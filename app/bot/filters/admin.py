"""Фильтр администратора: доступ только по ID из ADMIN_IDS."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message

from app.config import Settings, get_settings


class IsAdmin(BaseFilter):
    """Проверяет ID отправителя по ADMIN_IDS из настроек.

    Настройки подтягиваются лениво, чтобы фильтр можно было
    регистрировать без аргументов на этапе импорта роутера.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    async def __call__(self, message: Message) -> bool:
        settings = self._settings or get_settings()
        return (
            message.from_user is not None
            and message.from_user.id in settings.admin_ids
        )
