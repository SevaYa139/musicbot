"""Общий интерфейс адаптеров источников.

Каждый адаптер самостоятелен: определяет свои ссылки, получает метаданные,
умеет искать (если есть легальный API) и скачивать разрешённый контент.
Если адаптер сломался, остальные продолжают работать.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ProgressCallback = Callable[[int, str], None]
# (percent_or_-1, status_text); -1 означает «прогресс неизвестен, показать статус»


@dataclass(slots=True)
class MediaOption:
    """Один доступный вариант выдачи (разрешение видео или формат аудио)."""

    kind: Literal["video", "audio"]
    label: str
    option_id: str
    ext: str
    height: int | None = None
    note: str = ""


@dataclass(slots=True)
class TrackInfo:
    """Метаданные единицы контента — единый формат для всех источников."""

    source: str
    url: str
    title: str
    artist: str
    duration: float | None = None
    cover_url: str | None = None
    options: list[MediaOption] = field(default_factory=list)
    is_playlist: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DownloadResult:
    """Результат скачивания: готовый файл и его характеристики."""

    file_path: Path
    title: str
    artist: str
    duration: float | None
    cover_path: Path | None
    mime_hint: str  # audio/mpeg, video/mp4 ...


class SourceProvider(ABC):
    """Базовый класс адаптера источника."""

    name: str = "base"

    @abstractmethod
    def matches(self, url: str) -> bool:
        """Поддерживает ли адаптер эту ссылку."""

    @abstractmethod
    async def get_metadata(self, url: str) -> TrackInfo:
        """Метаданные единицы контента и доступные варианты выдачи.

        Бросает MetadataError / ContentUnavailableError по ситуации.
        """

    @abstractmethod
    async def download(
        self,
        info: TrackInfo,
        option: MediaOption,
        dest_dir: Path,
        on_progress: ProgressCallback | None = None,
    ) -> DownloadResult:
        """Скачивает контент выбранного варианта в dest_dir.

        Никогда не использует shell; внешние процессы — только argv-списком.
        """

    async def search(self, query: str, limit: int = 5) -> list[TrackInfo]:
        """Поиск по названию. По умолчанию не поддерживается."""
        return []
