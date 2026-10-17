"""Rate limiting: ограничение числа сообщений от одного пользователя."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import InlineQuery, Message, TelegramObject


class RateLimitMiddleware(BaseMiddleware):
    """Пропускает не больше N сообщений/инлайн-запросов в минуту с одного user_id."""

    def __init__(self, per_minute: int = 12) -> None:
        self._per_minute = per_minute
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._last_cleanup = time.monotonic()

    def _check(self, event: TelegramObject) -> bool:
        """True — лимит не превышен (и событие учтено)."""
        user = getattr(event, "from_user", None)
        if user is None:
            return True
        uid = user.id
        now = time.monotonic()
        # Периодическая чистка: словарь не должен расти бесконечно
        if now - self._last_cleanup > 3600:
            self._hits = defaultdict(
                deque, {k: v for k, v in self._hits.items() if v}
            )
            self._last_cleanup = now
        window = self._hits[uid]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self._per_minute:
            return False
        window.append(now)
        return True

    async def __call__(self, handler: Any, event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, Message):
            if not self._check(event):
                await event.answer(
                    "⏳ Слишком много запросов. Подожди немного и попробуй снова."
                )
                return None
        elif isinstance(event, InlineQuery) and not self._check(event):
            # Инлайн-поиск бьёт по 4 внешним API — без лимита это лёгкий DoS
            await event.answer([], cache_time=10, is_personal=True)
            return None
        return await handler(event, data)
