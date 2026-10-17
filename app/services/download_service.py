"""Оркестрация скачивания: изолированная папка, лимиты, конвертация, очистка."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.exceptions import MusicBotError
from app.providers.base import DownloadResult, MediaOption, ProgressCallback, TrackInfo
from app.providers.registry import ProviderRegistry
from app.services import media_converter
from app.utils.tempfiles import make_job_dir, remove_tree

log = logging.getLogger(__name__)


@dataclass(slots=True)
class FetchedMedia:
    """Готовый к отправке файл + его директория для последующей очистки."""

    result: DownloadResult
    job_dir: Path


class DownloadService:
    def __init__(self, settings: Settings, registry: ProviderRegistry) -> None:
        self._settings = settings
        self._registry = registry
        self._temp_root = settings.temp_dir
        self._temp_root.mkdir(parents=True, exist_ok=True)

    async def fetch(
        self,
        job_id: str,
        track: TrackInfo,
        option: MediaOption,
        on_progress: ProgressCallback | None = None,
    ) -> FetchedMedia:
        """Скачивает контент задания в изолированную директорию.

        Очистку временных файлов выполняет вызывающая сторона через cleanup()
        после отправки файла в Telegram (FSInputFile читает файл лениво).
        """
        provider = self._registry.get(track.source)
        job_dir = make_job_dir(self._temp_root, job_id)
        try:
            result = await provider.download(track, option, job_dir, on_progress)
            # Лимиты проверяем на реальном файле, а не на обещаниях метаданных
            await media_converter.check_limits(
                result.file_path,
                max_size_mb=self._settings.max_file_size_mb,
                max_duration_s=(
                    self._settings.max_video_duration_seconds
                    if option.kind == "video"
                    else None
                ),
            )
            if on_progress:
                on_progress(-1, "upload")
            return FetchedMedia(result=result, job_dir=job_dir)
        except MusicBotError:
            remove_tree(job_dir)
            raise
        except Exception as exc:
            log.exception("Непредвиденная ошибка загрузки job=%s", job_id)
            remove_tree(job_dir)
            raise MusicBotError("Внутренняя ошибка при обработке. Попробуйте ещё раз.") from exc
        except BaseException:
            # CancelledError по тайм-ауту/отмене: каталог обязан быть удалён,
            # иначе при каждом тайм-ауте будет течь диск.
            remove_tree(job_dir)
            raise

    def cleanup(self, job_dir: Path) -> None:
        """Удаляет временные файлы задания после отправки."""
        remove_tree(job_dir)
