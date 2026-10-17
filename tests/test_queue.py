"""Тесты очереди заданий: параллелизм, отмена, дедупликация, лимиты."""

import asyncio

import pytest
from app.exceptions import JobCancelledError, QueueFullError
from app.jobqueue.memory import MemoryJobQueue
from app.providers.base import MediaOption, TrackInfo


def _job(job_id: str, user_id: int = 1) -> "object":
    from app.jobqueue.base import JobRequest

    track = TrackInfo(source="youtube", url="https://youtu.be/x", title="T", artist="A")
    option = MediaOption(kind="audio", label="MP3", option_id="mp3-128", ext="mp3")
    return JobRequest(
        job_id=job_id, user_id=user_id, chat_id=user_id,
        status_message_id=1, track=track, option=option,
    )


async def test_enqueue_and_position() -> None:
    q = MemoryJobQueue(max_concurrent=1, max_pending=10)
    assert await q.enqueue(_job("j1")) == 1
    assert await q.enqueue(_job("j2")) == 2
    assert await q.position_of("j2") == 2
    assert await q.position_of("j1") == 1
    await q.close()


async def test_dedup_same_job() -> None:
    q = MemoryJobQueue(max_concurrent=1, max_pending=10)
    await q.enqueue(_job("j1"))
    pos = await q.enqueue(_job("j1"))  # повторное — не дублируется
    assert await q.size() == 1
    assert pos == 1
    await q.close()


async def test_queue_full() -> None:
    q = MemoryJobQueue(max_concurrent=1, max_pending=1)
    await q.enqueue(_job("j1"))
    with pytest.raises(QueueFullError):
        await q.enqueue(_job("j2"))
    await q.close()


async def test_concurrency_limit() -> None:
    q = MemoryJobQueue(max_concurrent=2, max_pending=10)
    running = 0
    max_running = 0

    async def worker() -> None:
        nonlocal running, max_running
        while (job := await q.get()) is not None:
            running += 1
            max_running = max(max_running, running)
            await asyncio.sleep(0.05)
            running -= 1
            await q.task_done(job)

    for i in range(6):
        await q.enqueue(_job(f"j{i}"))
    task = asyncio.create_task(worker())
    await asyncio.sleep(0.4)
    await q.close()
    await task
    assert max_running <= 2


async def test_cancel_pending_and_foreign_protection() -> None:
    q = MemoryJobQueue(max_concurrent=1, max_pending=10)
    await q.enqueue(_job("mine", user_id=1))
    await q.enqueue(_job("theirs", user_id=2))
    assert not await q.cancel("theirs", user_id=1)  # чужое нельзя
    assert await q.cancel("theirs", user_id=2)
    assert await q.cancel("mine", user_id=1)

    # Отменённые до старта задания НЕ выкидываются: воркер получает их
    # и сам финализирует (иначе статусное сообщение зависло бы в «очереди»).
    job = await asyncio.wait_for(q.get(), timeout=1)  # FIFO: сначала «mine»
    assert job is not None and job.job_id == "mine"
    assert q.is_cancelled("mine")
    await q.task_done(job)
    job2 = await asyncio.wait_for(q.get(), timeout=1)
    assert job2 is not None and job2.job_id == "theirs"
    await q.task_done(job2)
    await q.close()
    assert await q.get() is None
    # task_done финализирует задание и снимает флаг — утечки множества нет
    assert not q.is_cancelled("mine")


async def test_close_drains_queue() -> None:
    q = MemoryJobQueue(max_concurrent=1, max_pending=10)
    await q.enqueue(_job("j1"))
    done = []

    async def worker() -> None:
        while (job := await q.get()) is not None:
            done.append(job.job_id)
            await q.task_done(job)

    task = asyncio.create_task(worker())
    await asyncio.sleep(0.05)
    await q.close()
    await task
    assert done == ["j1"]


async def test_is_cancelled_via_interface() -> None:
    """Worker использует интерфейс is_cancelled — проверяем контракт."""
    q = MemoryJobQueue(max_concurrent=1, max_pending=10)
    await q.enqueue(_job("j1", user_id=1))
    assert not q.is_cancelled("j1")
    assert await q.cancel("j1", user_id=1)
    assert q.is_cancelled("j1")
    with pytest.raises(JobCancelledError):
        q.raise_if_cancelled("j1")
    await q.close()


async def test_base_interface_default_not_cancelled() -> None:
    from app.jobqueue.base import JobQueue

    assert JobQueue.is_cancelled(object(), "any") is False
