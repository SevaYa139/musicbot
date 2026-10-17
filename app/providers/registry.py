"""Реестр адаптеров источников: единая точка маршрутизации ссылок."""

from __future__ import annotations

from app.config import Settings
from app.exceptions import UnsupportedSourceError
from app.providers.base import SourceProvider
from app.providers.soundcloud import SoundCloudProvider
from app.providers.spotify import SpotifyProvider
from app.providers.tiktok import TikTokProvider
from app.providers.yandex_music import YandexMusicProvider
from app.providers.youtube import YouTubeProvider
from app.utils.urls import detect_source


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        proxy = settings.ytdlp_proxy
        self._providers: dict[str, SourceProvider] = {
            "youtube": YouTubeProvider(proxy),
            "soundcloud": SoundCloudProvider(proxy),
            "spotify": SpotifyProvider(settings),
            "yandex": YandexMusicProvider(settings),
            "tiktok": TikTokProvider(proxy),
        }

    def get(self, source: str) -> SourceProvider:
        try:
            return self._providers[source]
        except KeyError as exc:
            raise UnsupportedSourceError(f"Источник «{source}» не поддерживается.") from exc

    def resolve(self, url: str) -> SourceProvider:
        """Находит адаптер по ссылке."""
        source = detect_source(url)
        if source is None:
            raise UnsupportedSourceError(
                "Не удалось распознать ссылку. Поддерживаются YouTube, "
                "SoundCloud, Spotify, Яндекс Музыка и TikTok."
            )
        provider = self.get(source)
        if not provider.matches(url):
            raise UnsupportedSourceError("Такой тип ссылки источник не поддерживает.")
        return provider

    def providers(self) -> list[SourceProvider]:
        return list(self._providers.values())
