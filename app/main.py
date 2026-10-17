"""Точка входа: валидация конфигурации, сборка, polling + worker.

Запуск:
    python -m app.main
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.handlers import callbacks, commands, incoming, inline
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.bot.state import StateStore
from app.config import Settings, get_settings
from app.database.repository import Repository
from app.database.session import init_db, make_engine, make_session_factory
from app.jobqueue.base import JobQueue
from app.jobqueue.redis_queue import make_queue
from app.providers.registry import ProviderRegistry
from app.services.download_service import DownloadService
from app.services.search_service import SearchService
from app.utils.logging import setup_logging
from app.worker import worker_loop

log = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Открывает сессию БД на каждое обновление и пробрасывает репозиторий."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._factory() as session:
            data["repo"] = Repository(session)
            try:
                return await handler(event, data)
            finally:
                with contextlib.suppress(Exception):
                    await session.commit()


def build_dispatcher(
    settings: Settings,
    store: StateStore,
    job_queue: JobQueue,
    registry: ProviderRegistry,
    search_service: SearchService,
    session_factory: async_sessionmaker[AsyncSession],
) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(incoming.router)
    dp.include_router(inline.router)

    dp.workflow_data.update(
        settings=settings,
        store=store,
        job_queue=job_queue,
        registry=registry,
        search_service=search_service,
    )

    dp.update.outer_middleware(DbSessionMiddleware(session_factory))
    dp.message.outer_middleware(RateLimitMiddleware(settings.rate_limit_per_minute))
    dp.inline_query.outer_middleware(RateLimitMiddleware(settings.rate_limit_per_minute))
    return dp


async def main() -> None:
    setup_logging("INFO")
    settings = get_settings()
    log.info("Конфигурация загружена")

    engine = make_engine(settings.database_url)
    await init_db(engine)
    session_factory = make_session_factory(engine)

    registry = ProviderRegistry(settings)
    search_service = SearchService(registry)
    download_service = DownloadService(settings, registry)
    job_queue = make_queue(settings.redis_url, max_concurrent=settings.max_concurrent_jobs)
    store = StateStore()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(settings, store, job_queue, registry, search_service, session_factory)

    async def janitor() -> None:
        while True:
            await asyncio.sleep(300)
            store.purge_expired()
            try:
                async with session_factory() as session:
                    await Repository(session).purge_old_errors(days=14)
            except Exception:
                log.exception("janitor: не удалось почистить старые ошибки")

    janitor_task = asyncio.create_task(janitor())
    worker_task = asyncio.create_task(
        worker_loop(bot, job_queue, download_service, session_factory, settings)
    )

    log.info("Бот запущен (long polling)")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        janitor_task.cancel()
        await job_queue.close()  # дожидаемся активных заданий (graceful shutdown)
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        await bot.session.close()
        await engine.dispose()
        log.info("Остановлено корректно")


if __name__ == "__main__":
    asyncio.run(main())
