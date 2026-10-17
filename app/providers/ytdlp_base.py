"""Общая механика адаптеров на yt-dlp (YouTube, SoundCloud).

yt-dlp — синхронная библиотека, поэтому все вызовы оборачиваются в
asyncio.to_thread, чтобы не блокировать event loop. Внешний FFmpeg
вызывается только списком аргументов (без shell).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yt_dlp

from app.exceptions import (
    ContentUnavailableError,
    DownloadError,
    MetadataError,
)
from app.providers.base import (
    DownloadResult,
    MediaOption,
    ProgressCallback,
    SourceProvider,
    TrackInfo,
)

log = logging.getLogger(__name__)

VIDEO_HEIGHTS = (360, 480, 720, 1080, 1440, 2160)
AUDIO_QUALITIES = (
    ("mp3-320", "MP3 320 kbps"),
    ("mp3-192", "MP3 192 kbps"),
    ("mp3-128", "MP3 128 kbps"),
)

_COMMON_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 20,
    "retries": 2,
    "fragment_retries": 3,
    # Не скачиваем чужой контент через обход ограничений: только публичное.
    "cachedir": False,
}


class YtDlpProvider(SourceProvider):
    """База для провайдеров, работающих через yt-dlp."""

    def __init__(
        self, name: str, allowed_netlocs: tuple[str, ...], proxy: str | None = None
    ) -> None:
        self.name = name
        self._netlocs = allowed_netlocs
        self._proxy = proxy

    def _opts(self) -> dict[str, Any]:
        opts = dict(_COMMON_OPTS)
        if self._proxy:
            opts["proxy"] = self._proxy
        return opts

    # --- маршрутизация ---

    def matches(self, url: str) -> bool:
        from urllib.parse import urlparse

        host = (urlparse(url.strip()).hostname or "").lower()
        return any(host == n or host.endswith("." + n) for n in self._netlocs)

    # --- метаданные ---

    def _extract(self, url: str) -> dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL({**self._opts(), "skip_download": True}) as ydl:
                return ydl.extract_info(url, download=False)  # type: ignore[no-any-return]
        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc)
            if "blocked" in msg.lower():
                raise ContentUnavailableError(
                    f"{self.name}: источник заблокировал доступ с IP сервера. "
                    "Для этого источника нужен прокси (настройка YTDLP_PROXY)."
                ) from exc
            if any(
                marker in msg.lower()
                for marker in ("private", "sign in", "login", "forbidden", "age")
            ):
                raise ContentUnavailableError(
                    "Контент недоступен: он приватный, удалён или требует входа."
                ) from exc
            raise MetadataError(f"Не удалось получить информацию ({self.name}).") from exc
        except yt_dlp.utils.ExtractorError as exc:
            raise MetadataError(f"Источник не ответил корректно ({self.name}).") from exc

    def _build_options(self, info: dict[str, Any]) -> list[MediaOption]:
        """Собирает ТОЛЬКО реально доступные варианты из списка форматов."""
        formats = info.get("formats") or []
        heights = {
            int(f["height"])
            for f in formats
            if f.get("height") and f.get("vcodec", "none") != "none"
        }
        options: list[MediaOption] = []
        for h in VIDEO_HEIGHTS:
            if h in heights:
                label = f"{h}p"
                if h >= 1440:
                    label = "4K" if h >= 2160 else "QHD"
                elif h == 1080:
                    label = "Full HD"
                elif h == 720:
                    label = "HD"
                options.append(
                    MediaOption(kind="video", label=label, option_id=f"v{h}", ext="mp4", height=h)
                )
        # Аудио: честные форматы. Конвертация в 320k не улучшает исходник —
        # помечаем это в note.
        abr = max(
            (f.get("abr") or 0 for f in formats if f.get("acodec", "none") != "none"),
            default=0,
        )
        has_audio = abr > 0 or any(f.get("acodec", "none") != "none" for f in formats)
        if has_audio:
            note = (
                ""
                if abr >= 320
                else " (исходник ниже 320k — апскейл без прироста качества)"
            )
            for opt_id, label in AUDIO_QUALITIES:
                options.append(
                    MediaOption(
                        kind="audio", label=label, option_id=opt_id, ext="mp3", note=note
                    )
                )
            options.append(MediaOption(kind="audio", label="M4A", option_id="m4a", ext="m4a"))
            options.append(
                MediaOption(kind="audio", label="Оригинальная дорожка", option_id="orig", ext="")
            )
        return options

    async def get_metadata(self, url: str) -> TrackInfo:
        info = await asyncio.to_thread(self._extract, url)
        if info.get("_type") == "playlist":
            raise MetadataError(
                "Плейлисты пока не поддерживаются — отправьте ссылку на отдельный трек."
            )
        duration = info.get("duration")
        if duration and duration > 60 * 60:
            log.info("Длинный контент: %.0f сек, %s", duration, url)
        return TrackInfo(
            source=self.name,
            url=url,
            title=info.get("title") or "Без названия",
            artist=info.get("uploader") or info.get("channel") or "Неизвестный исполнитель",
            duration=duration,
            cover_url=(info.get("thumbnails") or [{}])[-1].get("url"),
            options=self._build_options(info),
            extra={"extractor": info.get("extractor_key", "")},
        )

    # --- скачивание ---

    def _progress_hook(self, cb: ProgressCallback | None) -> Any:
        if cb is None:
            return lambda _: None

        def hook(status: dict[str, Any]) -> None:
            if status.get("status") == "downloading":
                total = status.get("total_bytes") or status.get("total_bytes_estimate")
                done = status.get("downloaded_bytes") or 0
                if total:
                    cb(min(99, int(done * 100 / total)), "download")
                else:
                    cb(-1, "download")
            elif status.get("status") == "finished":
                cb(100, "process")

        return hook

    def _download_sync(
        self, info: TrackInfo, option: MediaOption, dest_dir: Path, cb: ProgressCallback | None
    ) -> DownloadResult:
        out_tmpl = str(dest_dir / "%(title).80B.%(ext)s")
        ydl_opts: dict[str, Any] = {
            **self._opts(),
            "outtmpl": out_tmpl,
            "restrictfilenames": True,
            "writethumbnail": True,  # обложка реальная, из источника
            "progress_hooks": [self._progress_hook(cb)],
        }
        if option.kind == "audio":
            ydl_opts["format"] = "bestaudio/best"
            if option.option_id.startswith("mp3-"):
                kbps = option.option_id.split("-")[1]
                ydl_opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": kbps,
                    }
                ]
            elif option.option_id == "m4a":
                ydl_opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "0"}
                ]
            # "orig": без постпроцессоров — оригинальная дорожка как есть
        else:
            h = option.height or 720
            ydl_opts["format"] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            ydl_opts["merge_output_format"] = "mp4"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([info.url])
        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc).lower()
            if any(m in msg for m in ("download disabled", "not downloadable", "forbidden")):
                raise ContentUnavailableError(
                    "Владелец отключил скачивание этого трека. Откройте оригинал в источнике."
                ) from exc
            raise DownloadError(
                f"Ошибка скачивания ({self.name}). Попробуйте другой формат."
            ) from exc

        files = sorted(dest_dir.iterdir(), key=lambda p: p.stat().st_size, reverse=True)
        files = [f for f in files if f.is_file() and not f.name.endswith((".part", ".ytdl"))]
        if not files:
            raise DownloadError("Файл не был сохранён — источник отказал.")
        media = files[0]
        cover = next(
            (f for f in files if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}),
            None,
        )
        mime = "audio/mpeg" if option.kind == "audio" else "video/mp4"
        if option.kind == "audio" and option.option_id == "m4a":
            mime = "audio/mp4"
        elif option.kind == "audio" and option.option_id == "orig":
            # MIME по фактическому расширению оригинальной дорожки
            mime = {
                ".webm": "audio/webm",
                ".opus": "audio/opus",
                ".m4a": "audio/mp4",
                ".mp3": "audio/mpeg",
                ".ogg": "audio/ogg",
                ".wav": "audio/wav",
            }.get(media.suffix.lower(), "audio/mpeg")
        return DownloadResult(
            file_path=media,
            title=info.title,
            artist=info.artist,
            duration=info.duration,
            cover_path=cover,
            mime_hint=mime,
        )

    async def download(
        self,
        info: TrackInfo,
        option: MediaOption,
        dest_dir: Path,
        on_progress: ProgressCallback | None = None,
    ) -> DownloadResult:
        return await asyncio.to_thread(self._download_sync, info, option, dest_dir, on_progress)

    # --- поиск ---

    #: префикс поиска yt-dlp: ytsearch для YouTube, scsearch для SoundCloud
    search_prefix = "ytsearch"

    async def search(self, query: str, limit: int = 5) -> list[TrackInfo]:
        """Поиск через yt-dlp. Без сети/при сбое возвращает пустой список."""
        return await asyncio.to_thread(self._search_sync, query, limit)

    def _search_sync(self, query: str, limit: int) -> list[TrackInfo]:
        try:
            with yt_dlp.YoutubeDL({**self._opts(), "skip_download": True}) as ydl:
                result = ydl.extract_info(f"{self.search_prefix}{limit}:{query}", download=False)
        except yt_dlp.utils.DownloadError:
            return []  # изоляция сбоя: поиск одного источника не ломает остальные
        entries = (result or {}).get("entries") or []
        tracks: list[TrackInfo] = []
        for entry in entries:
            if not entry or entry.get("_type") == "playlist":
                continue
            tracks.append(
                TrackInfo(
                    source=self.name,
                    url=entry.get("webpage_url") or entry.get("url") or "",
                    title=entry.get("title") or "Без названия",
                    artist=(
                        entry.get("uploader") or entry.get("channel") or "Неизвестный исполнитель"
                    ),
                    duration=entry.get("duration"),
                    cover_url=(entry.get("thumbnails") or [{}])[-1].get("url"),
                    options=self._build_options(entry),
                )
            )
            if len(tracks) >= limit:
                break
        return [t for t in tracks if t.url]
