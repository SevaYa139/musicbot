"""Worker: выполняет тяжёлые задания вне обработчика сообщений.

Каждое задание: прогресс в одном редактируемом сообщении (с ограничением
частоты обновлений), скачивание, проверка лимитов, отправка файла, очистка.
"""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import FSInputFile, InputFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot import texts
from app.config import Settings
from app.database.repository import Repository
from app.exceptions import JobCancelledError, MusicBotError
from app.jobqueue.base import JobQueue, JobRequest
from app.providers.base import DownloadResult
from app.services import media_converter
from app.services.download_service import DownloadService, FetchedMedia

log = logging.getLogger(__name__)

PROGRESS_MIN_INTERVAL = 2.0  # не чаще, чем раз в 2 секунды (rate limits Telegram)


class _StatusReporter:
    """Редактирует одно сообщение со статусом, душа частоту обновлений.

    Принимает ключи статусов (download/process/upload/...) и рендерит
    их с кастомными иконками из настроек.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        settings: Settings,
        subtitle: str = "",
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._message_id = message_id
        self._settings = settings
        self._subtitle = subtitle
        self._last_edit = 0.0
        self._pending: tuple[str, int, str] | None = None
        self._lock = asyncio.Lock()

    async def update(
        self, key: str, percent: int = -1, force: bool = False, label: str = ""
    ) -> None:
        async with self._lock:
            now = time.monotonic()
            self._pending = (key, percent, label)
            if not force and now - self._last_edit < PROGRESS_MIN_INTERVAL:
                return
            await self._flush()

    async def _flush(self) -> None:
        if self._pending is None:
            return
        key, percent, label = self._pending
        body = texts.status_line(self._settings, key, percent, label) + self._subtitle
        try:
            await self._bot.edit_message_text(
                body,
                chat_id=self._chat_id,
                message_id=self._message_id,
                parse_mode="HTML",
            )
            self._last_edit = time.monotonic()
            self._pending = None
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                self._pending = None
            else:
                log.debug("edit status failed: %s", exc)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)

    async def finish(self, key: str, label: str = "") -> None:
        await self.update(key, force=True, label=label)


async def process_job(
    bot: Bot,
    job: JobRequest,
    download_service: DownloadService,
    repo: Repository,
    job_queue: JobQueue,
    settings: Settings,
) -> None:
    """Полный цикл одного задания. Все ошибки обрабатываются внутри."""
    subtitle = (
        f"\n\n{texts._esc(job.track.title)} — {texts._esc(job.track.artist)}"
    )
    reporter = _StatusReporter(
        bot, job.chat_id, job.status_message_id, settings, subtitle=subtitle
    )
    fetched: FetchedMedia | None = None
    try:
        if job_queue.is_cancelled(job.job_id):
            raise JobCancelledError()  # отменено, пока ждало в очереди
        await repo.set_job_status(job.job_id, "running")
        await reporter.update("gear", label="Начинаю обработку...")
        loop = asyncio.get_running_loop()

        def on_progress(percent: int, status_key: str) -> None:
            if job_queue.is_cancelled(job.job_id):
                raise JobCancelledError()  # to_thread пробросит его в эту корутину
            # хук зовётся из потока yt-dlp — планируем корутину в главном loop
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(reporter.update(status_key, percent))
            )

        fetched = await asyncio.wait_for(
            download_service.fetch(job.job_id, job.track, job.option, on_progress),
            timeout=settings.job_timeout_seconds,
        )
        if job_queue.is_cancelled(job.job_id):
            raise JobCancelledError()

        # Отправка файла не должна ронять задание: при сбое отправки
        # файл можно перечитать с диска, поэтому ловим отдельно.
        try:
            await _send_result(bot, job, fetched.result)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            await _send_result(bot, job, fetched.result)
        await repo.set_job_status(job.job_id, "done")
        await repo.bump_jobs(job.user_id, success=True)
        await reporter.finish("check", label="Готово! Файл отправлен выше.")
    except JobCancelledError:
        await repo.set_job_status(job.job_id, "cancelled")
        await reporter.finish("cross", label="Задание отменено.")
    except TimeoutError:
        await _fail(repo, reporter, job, "Задание превысило лимит времени и было остановлено.")
    except MusicBotError as exc:
        await _fail(repo, reporter, job, str(exc))
    except Exception as exc:
        log.exception("job %s failed unexpectedly", job.job_id)
        await repo.log_error(type(exc).__name__, job_id=job.job_id, source=job.track.source)
        await _fail(repo, reporter, job, "Внутренняя ошибка. Попробуйте позже.")
    finally:
        if fetched is not None:
            download_service.cleanup(fetched.job_dir)


async def _fail(repo: Repository, reporter: _StatusReporter, job: JobRequest, text: str) -> None:
    await repo.set_job_status(job.job_id, "failed", error=text[:200])
    await repo.bump_jobs(job.user_id, success=False)
    await repo.log_error(text[:200], job_id=job.job_id, source=job.track.source)
    await reporter.finish("cross", label=text)


async def _send_result(bot: Bot, job: JobRequest, result: DownloadResult) -> None:
    media_file: InputFile = FSInputFile(result.file_path)
    title = result.title[:64]
    caption = f"{texts._esc(result.artist)} — {texts._esc(title)}"
    thumb: InputFile | None = None
    if result.cover_path and result.cover_path.exists():
        # Telegram принимает миниатюры только в JPEG ≤320px; исходники
        # чаще всего webp/png — конвертируем через FFmpeg.
        jpg = await media_converter.make_telegram_thumbnail(
            result.cover_path, result.file_path.parent
        )
        if jpg is not None:
            thumb = FSInputFile(jpg)

    if result.mime_hint.startswith("audio"):
        await bot.send_audio(
            chat_id=job.chat_id,
            audio=media_file,
            caption=caption,
            parse_mode="HTML",
            title=title,
            performer=result.artist[:64],
            thumbnail=thumb,
        )
    else:
        await bot.send_video(
            chat_id=job.chat_id,
            video=media_file,
            caption=caption,
            parse_mode="HTML",
            supports_streaming=True,
            thumbnail=thumb,
        )


async def worker_loop(
    bot: Bot,
    job_queue: JobQueue,
    download_service: DownloadService,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Бесконечный цикл worker'а; корректно завершается по close()."""
    from app.database.repository import Repository

    while True:
        try:
            job = await job_queue.get()
        except Exception:
            # Сбой очереди (например, Redis недоступен) не должен убивать worker
            log.exception("worker: ошибка чтения очереди, повтор через 5 секунд")
            await asyncio.sleep(5)
            continue
        if job is None:
            break
        async with session_factory() as session:
            repo = Repository(session)
            try:
                await process_job(bot, job, download_service, repo, job_queue, settings)
            except Exception:
                # process_job ловит почти всё, но не TelegramRetryAfter из репортера
                # и ошибки БД — worker обязан пережить такое.
                log.exception("worker: задание %s рухнуло вне process_job", job.job_id)
            finally:
                await job_queue.task_done(job)
