"""Адаптер Spotify: метаданные и поиск через официальный API.

Spotify не отдаёт полные аудиофайлы через обычный API. Бот показывает
метаданные и предлагает открыть оригинал — без подмены превью полной песней
и без обхода ограничений платформы.
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
from app.utils.urls import format_duration

_TRACK_RE = re.compile(r"^https?://open\.spotify\.com/track/[\w]+", re.IGNORECASE)


class SpotifyProvider(SourceProvider):
    name = "spotify"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not (self._settings.spotify_client_id and self._settings.spotify_client_secret):
            raise MetadataError(
                "Spotify не настроен администратором (SPOTIFY_CLIENT_ID/SECRET)."
            )
        import spotipy  # локальный импорт: без настроек библиотека не нужна

        self._client = spotipy.Spotify(
            auth_manager=spotipy.SpotifyClientCredentials(
                client_id=self._settings.spotify_client_id,
                client_secret=self._settings.spotify_client_secret,
            )
        )
        return self._client

    def matches(self, url: str) -> bool:
        return bool(_TRACK_RE.match(url.strip()))

    def _to_track_info(self, track: dict[str, Any]) -> TrackInfo:
        artists = (
            ", ".join(a["name"] for a in track.get("artists", []))
            or "Неизвестный исполнитель"
        )
        cover = None
        images = (track.get("album") or {}).get("images") or []
        if images:
            cover = images[0]["url"]
        return TrackInfo(
            source=self.name,
            url=track["external_urls"]["spotify"],
            title=track.get("name") or "Без названия",
            artist=artists,
            duration=(track.get("duration_ms") or 0) / 1000 or None,
            cover_url=cover,
            options=[
                MediaOption(
                    kind="audio",
                    label="Открыть в Spotify",
                    option_id="open",
                    ext="",
                    note="Полное аудио доступно только в Spotify",
                )
            ],
        )

    async def get_metadata(self, url: str) -> TrackInfo:
        track_id = url.rstrip("/").split("/")[-1].split("?")[0]
        try:
            track = await asyncio.to_thread(self._get_client().track, track_id)
        except Exception as exc:
            raise MetadataError("Не удалось получить трек Spotify.") from exc
        return self._to_track_info(track)

    async def search(self, query: str, limit: int = 5) -> list[TrackInfo]:
        try:
            result = await asyncio.to_thread(
                self._get_client().search, query, limit=limit, type="track"
            )
        except Exception as exc:
            raise SearchError("Поиск Spotify временно недоступен.") from exc
        items = (result or {}).get("tracks", {}).get("items", [])
        return [self._to_track_info(t) for t in items]

    async def download(
        self,
        info: TrackInfo,
        option: MediaOption,
        dest_dir: Path,
        on_progress: ProgressCallback | None = None,
    ) -> DownloadResult:
        raise ContentUnavailableError(
            "Spotify не предоставляет аудиофайлы через API.\n"
            f"🎧 {info.artist} — {info.title} ({format_duration(info.duration)})\n"
            "Откройте трек в официальном приложении: " + info.url
        )
