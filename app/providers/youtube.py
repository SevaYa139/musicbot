"""Адаптер YouTube: обычные видео, Shorts, ссылки с таймкодами, youtu.be."""

from __future__ import annotations

import re

from app.providers.ytdlp_base import YtDlpProvider

_SHORTS_RE = re.compile(r"^https?://(www\.)?youtube\.com/shorts/[\w-]+", re.IGNORECASE)


class YouTubeProvider(YtDlpProvider):
    name = "youtube"

    def __init__(self, proxy: str | None = None) -> None:
        super().__init__(
            name="youtube",
            allowed_netlocs=("youtube.com", "youtu.be", "music.youtube.com"),
            proxy=proxy,
        )

    def matches(self, url: str) -> bool:
        if _SHORTS_RE.match(url.strip()):
            return True
        return super().matches(url)
