"""Поиск по названию: опрашивает все адаптеры, у которых есть легальный поиск."""

from __future__ import annotations

import asyncio
import logging

from app.providers.base import TrackInfo
from app.providers.registry import ProviderRegistry

log = logging.getLogger(__name__)


class SearchService:
    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    async def search(self, query: str, per_source: int = 3) -> list[TrackInfo]:
        """Возвращает объединённые результаты; сбой одного источника другим не мешает."""

        async def safe_search(name: str) -> list[TrackInfo]:
            try:
                provider = self._registry.get(name)
                return await provider.search(query, limit=per_source)
            except Exception as exc:
                log.warning("Поиск %s недоступен: %s", name, exc)
                return []

        results = await asyncio.gather(
            safe_search("youtube"),
            safe_search("soundcloud"),
            safe_search("spotify"),
            safe_search("yandex"),
            return_exceptions=False,
        )
        merged: list[TrackInfo] = []
        for part in results:
            merged.extend(part)
        return merged
