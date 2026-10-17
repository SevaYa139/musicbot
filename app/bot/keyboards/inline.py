"""Инлайн-клавиатуры. Callback-данные компактные и проверяемые.

Формат callback: prefix:state_id:payload — без доверия к чужим данным.
Право доступа к состоянию всегда проверяется по user_id в StateStore.
Кнопки несут иконки премиум-пакета через icon_custom_emoji_id (Bot API 9.4+).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TypedDict

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import Settings, get_settings
from app.providers.base import TrackInfo

PREFIX = "mb"


class _BtnIcon(TypedDict, total=False):
    icon_custom_emoji_id: str


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return get_settings()


def _btn_icon(key: str) -> _BtnIcon:
    """icon_custom_emoji_id для кнопки, если id иконки задан в конфиге."""
    s = _settings()
    icons = {
        "music": s.custom_emoji_music,
        "video": s.custom_emoji_video,
        "search": s.custom_emoji_search,
        "cross": s.custom_emoji_cross,
        "link": s.custom_emoji_link,
        "play": s.custom_emoji_play,
    }
    emoji_id = icons.get(key)
    return {"icon_custom_emoji_id": emoji_id} if emoji_id else {}


def cancel_keyboard(state_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"{PREFIX}:cancel:{state_id}",
                    **_btn_icon("cross"),
                )
            ]
        ]
    )


def media_type_keyboard(state_id: str, track: TrackInfo) -> InlineKeyboardMarkup:
    """Аудио / Видео — только если такие варианты реально есть."""
    has_audio = any(o.kind == "audio" and o.option_id != "open" for o in track.options)
    has_video = any(o.kind == "video" for o in track.options)
    rows: list[list[InlineKeyboardButton]] = []
    main_row: list[InlineKeyboardButton] = []
    if has_audio:
        main_row.append(
            InlineKeyboardButton(
                text="Аудио",
                callback_data=f"{PREFIX}:type:{state_id}:audio",
                **_btn_icon("music"),
            )
        )
    if has_video:
        main_row.append(
            InlineKeyboardButton(
                text="Видео",
                callback_data=f"{PREFIX}:type:{state_id}:video",
                **_btn_icon("video"),
            )
        )
    if main_row:
        rows.append(main_row)
    rows.append(_original_row(state_id, track))
    rows.append(
        [
            InlineKeyboardButton(
                text="Отмена",
                callback_data=f"{PREFIX}:cancel:{state_id}",
                **_btn_icon("cross"),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def options_keyboard(state_id: str, track: TrackInfo, kind: str) -> InlineKeyboardMarkup:
    """Доступные разрешения/форматы — по 3 в ряд, без фиктивных кнопок."""
    options = [o for o in track.options if o.kind == kind and o.option_id != "open"]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for opt in options:
        row.append(
            InlineKeyboardButton(
                text=opt.label, callback_data=f"{PREFIX}:opt:{state_id}:{opt.option_id}"
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    back_row = [
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"{PREFIX}:back:{state_id}")
    ]
    back_row.append(
        InlineKeyboardButton(
            text="Отмена",
            callback_data=f"{PREFIX}:cancel:{state_id}",
            **_btn_icon("cross"),
        )
    )
    rows.append(back_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_job_keyboard(job_id: str, state_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отменить загрузку",
                    callback_data=f"{PREFIX}:canceljob:{job_id}:{state_id}",
                    **_btn_icon("cross"),
                )
            ]
        ]
    )


def search_results_keyboard(
    state_ids: list[tuple[str, TrackInfo]],
) -> InlineKeyboardMarkup:
    """По одной кнопке на результат поиска."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"{t.artist} — {t.title}"[:64],
                callback_data=f"{PREFIX}:pick:{sid}",
                **_btn_icon("play"),
            )
        ]
        for sid, t in state_ids
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _original_row(state_id: str, track: TrackInfo) -> list[InlineKeyboardButton]:
    open_opt = next((o for o in track.options if o.option_id == "open"), None)
    icon = _btn_icon("link")
    if open_opt:
        return [InlineKeyboardButton(text="Открыть оригинал", url=track.url, **icon)]
    return [
        InlineKeyboardButton(text="Открыть оригинал", url=track.url, **icon),
        InlineKeyboardButton(
            text="ℹ️ Почему нет файла?", callback_data=f"{PREFIX}:why:{state_id}"
        ),
    ]
