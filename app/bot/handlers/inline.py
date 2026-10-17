"""Инлайн-режим: @SaveStati_bot <запрос> в любом чате.

Результат-статья со ссылкой на трек: при выборе в чат уходит ссылка,
и обычный сценарий бота (карточка → выбор формата → файл) продолжается
как по прямой отправке ссылки боту.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultUnion,
    InputTextMessageContent,
)

from app.bot import texts
from app.bot.keyboards.inline import _btn_icon
from app.config import Settings
from app.providers.base import TrackInfo
from app.services.search_service import SearchService
from app.utils.urls import format_duration

log = logging.getLogger(__name__)
router = Router()

MIN_QUERY_LEN = 2
MAX_RESULTS = 8


def _article(idx: int, track: TrackInfo) -> InlineQueryResultArticle:
    source = texts.SOURCE_NAMES.get(track.source, track.source)
    return InlineQueryResultArticle(
        id=f"{track.source}-{idx}",
        title=track.title[:120] or "Без названия",
        description=(
            f"{track.artist} • {source} • {format_duration(track.duration)}"
        )[:200],
        input_message_content=InputTextMessageContent(message_text=track.url),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Открыть в {source}",
                        url=track.url,
                        **_btn_icon("play"),
                    )
                ]
            ]
        ),
    )


@router.inline_query()
async def inline_search(
    query: InlineQuery, settings: Settings, search_service: SearchService
) -> None:
    q = (query.query or "").strip()
    if len(q) < MIN_QUERY_LEN:
        await query.answer(
            [],
            cache_time=10,
            is_personal=True,
            switch_pm_text="Открыть бота и прислать ссылку",
            switch_pm_parameter="inline",
        )
        return

    try:
        tracks = await search_service.search(q, per_source=2)
    except Exception as exc:  # инлайн не должен падать — это просто подсказка
        log.warning("Инлайн-поиск не удался: %s", exc)
        tracks = []

    results: list[InlineQueryResultUnion] = [
        _article(i, t) for i, t in enumerate(tracks[:MAX_RESULTS])
    ]
    await query.answer(results, cache_time=300, is_personal=True)
