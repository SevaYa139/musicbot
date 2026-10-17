"""Адаптер Яндекс Музыки: метаданные через официальную библиотеку.

Без OAuth-токена — только метаданные публичных страниц и ссылка на оригинал.
DRM и подписочные ограничения не обходятся никогда.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from app.config import Settings
from app.exceptions import ContentUnavailableError, MetadataError, SearchError
from app.providers.base import (
    DownloadResult,
    MediaOption,
    ProgressCallback,
    SourceProvider,
    TrackInfo,
)

_TRACK_RE = re.compile(r"^https?://music\.yandex\.[a-z.]+/track/(\d+)", re.IGNORECASE)


class YandexMusicProvider(SourceProvider):
    name = "yandex"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            from yandex_music import Client  # локальный импорт

            self._client = (
                Client(self._settings.yandex_token)
                if self._settings.yandex_token
                else Client()
            )
        return self._client

    def matches(self, url: str) -> bool:
        return bool(_TRACK_RE.match(url.strip()))

    def _to_track_info(self, track: Any) -> TrackInfo:
        artists = ", ".join(a.name for a in (track.artists or [])) or "Неизвестный исполнитель"
        cover = None
        if track.cover_uri:
            cover = "https://" + track.cover_uri.replace("%%", "400x400")
        return TrackInfo(
            source=self.name,
            url=f"https://music.yandex.ru/track/{track.id}",
            title=track.title or "Без названия",
            artist=artists,
            duration=track.duration_ms / 1000 if track.duration_ms else None,
            cover_url=cover,
            options=[
                MediaOption(
                    kind="audio",
                    label="Открыть в Яндекс Музыке",
                    option_id="open",
                    ext="",
                    note="Скачивание требует авторизации",
                )
            ],
        )

    async def get_metadata(self, url: str) -> TrackInfo:
        m = _TRACK_RE.match(url.strip())
        if not m:
            raise MetadataError("Не удалось распознать ссылку Яндекс Музыки.")
        try:
            track = await asyncio.to_thread(self._get_client().tracks, [int(m.group(1))])
            track = track[0]
        except Exception as exc:
            raise MetadataError(
                "Не удалось получить трек Яндекс Музыки. Возможно, он доступен только по подписке."
            ) from exc
        return self._to_track_info(track)

    async def search(self, query: str, limit: int = 5) -> list[TrackInfo]:
        try:
            result = await asyncio.to_thread(self._get_client().search, query, type_="track")
        except Exception as exc:
            raise SearchError("Поиск Яндекс Музыки временно недоступен.") from exc
        best = (result or None) and getattr(result, "best", None)
        tracks = getattr(best, "result", None) or []
        return [self._to_track_info(t) for t in tracks[:limit]]

    async def download(
        self,
        info: TrackInfo,
        option: MediaOption,
        dest_dir: Path,
        on_progress: ProgressCallback | None = None,
    ) -> DownloadResult:
        raise ContentUnavailableError(
            "Скачивание из Яндекс Музыки недоступно без авторизации.\n"
            "Откройте трек в официальном приложении: " + info.url
        )
