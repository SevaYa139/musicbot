"""In-memory очередь с ограничением параллелизма, отменой и дедупликацией."""

from __future__ import annotations

import asyncio
import logging

from app.exceptions import JobCancelledError, QueueFullError
from app.jobqueue.base import JobQueue, JobRequest

log = logging.getLogger(__name__)


class MemoryJobQueue(JobQueue):
    def __init__(self, max_concurrent: int = 3, max_pending: int = 100) -> None:
        self._queue: asyncio.Queue[JobRequest] = asyncio.Queue(maxsize=max_pending)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._closed = False
        self._cancelled: set[str] = set()
        self._inflight: dict[str, JobRequest] = {}
        self._inflight_count = 0
        self._drained = asyncio.Event()
        self._drained.set()

    async def enqueue(self, job: JobRequest) -> int:
        if self._closed:
            raise QueueFullError("Очередь остановлена, попробуйте позже.")
        # Защита от повторного выполнения одного задания
        if job.job_id in self._inflight or any(
            j.job_id == job.job_id
            for j in list(self._queue._queue)  # type: ignore[attr-defined]
        ):
            return await self.position_of(job.job_id)
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull as exc:
            raise QueueFullError(
                "Сервер перегружен — задача не влезла в очередь. Попробуйте через минуту."
            ) from exc
        return self._queue.qsize()  # позиция с 1: 1 = первое в очереди

    async def get(self) -> JobRequest | None:
        """Блокируется до появления задания; None когда закрыто и опустошено.

        Отменённые до старта задания НЕ выкидываются здесь: воркер получает
        их и финализирует (статус в БД и статусное сообщение пользователя),
        иначе сообщение зависло бы на «в очереди» навсегда.
        """
        while True:
            if self._closed and self._queue.empty():
                return None
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            self._queue.task_done()
            await self._semaphore.acquire()
            self._inflight[job.job_id] = job
            self._inflight_count += 1
            self._drained.clear()
            return job

    async def task_done(self, job: JobRequest) -> None:
        self._inflight.pop(job.job_id, None)
        self._cancelled.discard(job.job_id)
        self._semaphore.release()
        self._inflight_count -= 1
        if self._inflight_count <= 0:
            self._inflight_count = 0
            self._drained.set()

    async def position_of(self, job_id: str) -> int:
        if job_id in self._inflight:
            return 0
        for idx, j in enumerate(list(self._queue._queue)):  # type: ignore[attr-defined]
            if j.job_id == job_id:
                return idx + 1
        return -1

    async def size(self) -> int:
        return self._queue.qsize()

    async def cancel(self, job_id: str, user_id: int) -> bool:
        """Отмена ожидающего задания. Выполняющееся останавливается флагом."""
        job = self._inflight.get(job_id)
        if job is not None:
            if job.user_id != user_id:
                return False
            self._cancelled.add(job_id)  # worker проверяет флаг между этапами
            return True
        for j in list(self._queue._queue):  # type: ignore[attr-defined]
            if j.job_id == job_id:
                if j.user_id != user_id:
                    return False  # чужое задание трогать нельзя
                self._cancelled.add(job_id)
                return True
        return False

    def is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancelled

    def raise_if_cancelled(self, job_id: str) -> None:
        if self.is_cancelled(job_id):
            raise JobCancelledError("Задание отменено.")

    async def close(self) -> None:
        """Прекращает приём и дожидается только выполняющихся заданий.

        Невыполненные задания из очереди сбрасываются: worker'ы завершат цикл,
        как только очередь опустеет и флаг _closed выставлен.
        """
        self._closed = True
        try:
            await asyncio.wait_for(self._drained.wait(), timeout=60)
        except TimeoutError:
            log.warning("Активные задания не завершились за 60 секунд при shutdown")
