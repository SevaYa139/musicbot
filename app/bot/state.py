"""Временное состояние диалогов в памяти процесса.

Хранит карточки контента между callback-нажатиями. Живёт недолго,
ничего персонального сверх необходимого, очищается TTL-ом.
В проде с Redis это можно вынести в него — интерфейс тот же.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.providers.base import TrackInfo


@dataclass(slots=True)
class DialogState:
    """Состояние диалога одного пользователя."""

    track: TrackInfo
    user_id: int
    created_at: float = field(default_factory=time.monotonic)


class StateStore:
    """In-memory хранилище состояний с TTL и изоляцией по пользователю."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._data: dict[str, DialogState] = {}
        self._flags: dict[int, tuple[str, float]] = {}

    def set(self, state_id: str, state: DialogState) -> None:
        self._data[state_id] = state

    # --- простые флаги режима (например, ожидание текста баг-репорта) ---

    def set_flag(self, user_id: int, flag: str) -> None:
        self._flags[user_id] = (flag, time.monotonic())

    def get_flag(self, user_id: int) -> str | None:
        entry = self._flags.get(user_id)
        if entry is None:
            return None
        flag, created = entry
        if time.monotonic() - created > self._ttl:
            self._flags.pop(user_id, None)
            return None
        return flag

    def drop_flag(self, user_id: int) -> None:
        self._flags.pop(user_id, None)

    def get(self, state_id: str, user_id: int) -> DialogState | None:
        """Возвращает состояние только владельцу — чужие задания недоступны."""
        state = self._data.get(state_id)
        if state is None or state.user_id != user_id:
            return None
        if time.monotonic() - state.created_at > self._ttl:
            self._data.pop(state_id, None)
            return None
        return state

    def drop(self, state_id: str) -> None:
        self._data.pop(state_id, None)

    def purge_expired(self) -> int:
        now = time.monotonic()
        expired = [
            sid
            for sid, s in self._data.items()
            if now - s.created_at > self._ttl
        ]
        for sid in expired:
            self._data.pop(sid, None)
        stale_flags = [uid for uid, (_, t) in self._flags.items() if now - t > self._ttl]
        for uid in stale_flags:
            self._flags.pop(uid, None)
        return len(expired)
