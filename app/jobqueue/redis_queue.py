"""Очередь с семафором параллелизма, отменой и дедупликацией.

Используется Redis (если задан REDIS_URL) только для дедупликации job_id
между перезапусками. Сама очередь и флаги отмены — в памяти процесса;
бот работает в одном процессе, распределённой отмены не требуется.
"""

from __future__ import annotations

import logging
from typing import Any

from app.jobqueue.base import JobQueue, JobRequest
from app.jobqueue.memory import MemoryJobQueue

log = logging.getLogger(__name__)


def make_queue(redis_url: str | None, max_concurrent: int, max_pending: int = 100) -> JobQueue:
    """Фабрика: Redis при наличии URL, иначе in-memory."""
    if redis_url:
        try:
            return RedisJobQueue(redis_url, max_concurrent, max_pending)
        except Exception as exc:
            log.warning("Redis недоступен (%s), откатываюсь на in-memory очередь", exc)
    return MemoryJobQueue(max_concurrent, max_pending)


class RedisJobQueue(JobQueue):
    """Обёртка: очередь и отмена в памяти, Redis — дедупликация job_id."""

    def __init__(self, redis_url: str, max_concurrent: int, max_pending: int = 100) -> None:
        import redis.asyncio as aioredis

        self._redis: Any = aioredis.from_url(redis_url, decode_responses=True)
        self._inner = MemoryJobQueue(max_concurrent, max_pending)

    async def enqueue(self, job: JobRequest) -> int:
        key = f"musicbot:job:{job.job_id}"
        if await self._redis.set(key, "1", nx=True, ex=24 * 3600) is None:
            return await self._inner.position_of(job.job_id)
        return await self._inner.enqueue(job)

    async def get(self) -> JobRequest | None:
        return await self._inner.get()

    async def task_done(self, job: JobRequest) -> None:
        await self._redis.delete(f"musicbot:job:{job.job_id}")
        await self._inner.task_done(job)

    async def position_of(self, job_id: str) -> int:
        return await self._inner.position_of(job_id)

    async def size(self) -> int:
        return await self._inner.size()

    async def cancel(self, job_id: str, user_id: int) -> bool:
        return await self._inner.cancel(job_id, user_id)

    def is_cancelled(self, job_id: str) -> bool:
        return self._inner.is_cancelled(job_id)

    async def close(self) -> None:
        await self._inner.close()
        await self._redis.aclose()
