"""Адаптер TikTok: обычные видео, клипы и короткие ссылки vm/vt.tiktok.com.

Основной путь — публичный API tikwm.com: запрос к TikTok уходит с серверов
tikwm, поэтому блокировка датацентрового IP VPS не мешает. Если tikwm
недоступен — fallback на yt-dlp (работает, если задан YTDLP_PROXY).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

from app.exceptions import DownloadError, MetadataError
from app.providers.base import DownloadResult, MediaOption, ProgressCallback, TrackInfo
from app.providers.ytdlp_base import YtDlpProvider

log = logging.getLogger(__name__)

_TIKWM_API = "https://www.tikwm.com/api/"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_BAD_FILENAME = re.compile(r"[^\w .&()\-]+", re.UNICODE)


def _ext_of(url: str, default: str) -> str:
    path = urllib.parse.urlparse(url).path
    ext = Path(path).suffix.lower().lstrip(".")
    return ext if ext in {"mp4", "mp3", "m4a", "webm", "mov"} else default


def _save_name(title: str, ext: str) -> str:
    stem = _BAD_FILENAME.sub("_", title).strip(" ._")[:80] or "tiktok"
    return f"{stem}.{ext}"


class TikTokProvider(YtDlpProvider):
    name = "tiktok"

    def __init__(self, proxy: str | None = None) -> None:
        super().__init__(
            name="tiktok",
            allowed_netlocs=(
                "tiktok.com",
                "www.tiktok.com",
                "m.tiktok.com",
                "vm.tiktok.com",
                "vt.tiktok.com",
            ),
            proxy=proxy,
        )

    # --- метаданные ---

    async def get_metadata(self, url: str) -> TrackInfo:
        try:
            return await asyncio.to_thread(self._via_tikwm, url)
        except MetadataError as exc:
            log.info("tikwm недоступен (%s), пробую yt-dlp", exc)
            return await super().get_metadata(url)

    def _tikwm_api(self, url: str) -> dict[str, Any]:
        api = _TIKWM_API + "?" + urllib.parse.urlencode({"url": url})
        req = urllib.request.Request(api, headers={"User-Agent": _UA})  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310
                payload = json.loads(resp.read())
        except Exception as exc:
            raise MetadataError(f"TikTok API не ответил: {exc}") from exc
        if payload.get("code") != 0 or not payload.get("data"):
            msg = (payload.get("msg") or "неизвестная ошибка API").strip()
            raise MetadataError(f"TikTok API: {msg}")
        return cast("dict[str, Any]", payload["data"])

    def _via_tikwm(self, url: str) -> TrackInfo:
        data = self._tikwm_api(url)
        if not data.get("play"):
            raise MetadataError("TikTok API не вернул ссылку на видео.")
        options = [
            MediaOption(kind="video", label="SD", option_id="vsd", ext="mp4", height=576),
        ]
        if data.get("hdplay"):
            options.append(
                MediaOption(kind="video", label="HD", option_id="vhd", ext="mp4", height=1080)
            )
        if data.get("music"):
            ext = _ext_of(data["music"], "mp3")
            options.append(
                MediaOption(
                    kind="audio",
                    label="Оригинальная музыка",
                    option_id="orig",
                    ext=ext,
                    note="аудиодорожка из видео",
                )
            )
        author = (data.get("author") or {}).get("nickname") or "TikTok"
        return TrackInfo(
            source=self.name,
            url=url,
            title=data.get("title") or "TikTok-видео",
            artist=author,
            duration=data.get("duration"),
            cover_url=data.get("cover"),
            options=options,
            extra={"tikwm": data},
        )

    # --- скачивание ---

    async def download(
        self,
        info: TrackInfo,
        option: MediaOption,
        dest_dir: Path,
        on_progress: ProgressCallback | None = None,
    ) -> DownloadResult:
        tw = info.extra.get("tikwm")
        if isinstance(tw, dict) and tw:
            return await asyncio.to_thread(
                self._download_tikwm, info, option, dest_dir, tw, on_progress
            )
        return await super().download(info, option, dest_dir, on_progress)

    def _download_tikwm(
        self,
        info: TrackInfo,
        option: MediaOption,
        dest_dir: Path,
        tw: dict[str, Any],
        cb: ProgressCallback | None,
    ) -> DownloadResult:
        if option.kind == "audio":
            media_url = tw.get("music")
            default_ext = "mp3"
        else:
            media_url = tw.get("hdplay") if option.option_id == "vhd" else tw.get("play")
            default_ext = "mp4"
        if not media_url:
            raise DownloadError("TikTok API не дал ссылку на выбранный формат.")

        ext = _ext_of(media_url, default_ext)
        media_path = dest_dir / _save_name(info.title, ext)
        self._fetch_file(media_url, media_path, cb)

        cover_path: Path | None = None
        if tw.get("cover"):
            try:
                cover_path = dest_dir / "cover.jpg"
                self._fetch_file(tw["cover"], cover_path, None)
            except DownloadError:
                cover_path = None  # обложка — необязательна

        mime = (
            "video/mp4"
            if option.kind == "video"
            else {"mp3": "audio/mpeg", "m4a": "audio/mp4", "webm": "audio/webm"}.get(
                ext, "audio/mpeg"
            )
        )
        return DownloadResult(
            file_path=media_path,
            title=info.title,
            artist=info.artist,
            duration=info.duration,
            cover_path=cover_path,
            mime_hint=mime,
        )

    def _fetch_file(
        self, url: str, dest: Path, cb: ProgressCallback | None
    ) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:  # noqa: S310
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if cb and total:
                        cb(min(99, int(done * 100 / total)), "download")
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise DownloadError(f"Не удалось скачать файл с TikTok API: {exc}") from exc
        if cb:
            cb(100, "process")
