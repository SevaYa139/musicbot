"""Адаптер SoundCloud: треки и публичные плейлисты.

Если владелец отключил скачивание, бот честно сообщает об этом
и не пытается обходить ограничение.
"""

from __future__ import annotations

from app.providers.ytdlp_base import YtDlpProvider


class SoundCloudProvider(YtDlpProvider):
    name = "soundcloud"
    search_prefix = "scsearch"

    def __init__(self, proxy: str | None = None) -> None:
        super().__init__(name="soundcloud", allowed_netlocs=("soundcloud.com",), proxy=proxy)
