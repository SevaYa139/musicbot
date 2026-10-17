"""Обработчики callback-запросов: выбор формата, отмена, навигация.

Каждый callback проверяет владельца состояния — чужие задания недоступны.
"""

from __future__ import annotations

import contextlib
import logging
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, InaccessibleMessage, Message

from app.bot import texts
from app.bot.keyboards.inline import (
    PREFIX,
    cancel_job_keyboard,
    media_type_keyboard,
    options_keyboard,
)
from app.bot.keyboards.menu import (
    MENU_BACK,
    MENU_BUG,
    MENU_FAQ,
    MENU_MUSIC,
    MENU_VIDEO,
    back_keyboard,
    menu_inline_keyboard,
)
from app.bot.state import DialogState, StateStore
from app.config import Settings
from app.database.models import Job
from app.database.repository import Repository
from app.exceptions import MusicBotError
from app.jobqueue.base import JobQueue, JobRequest

log = logging.getLogger(__name__)
router = Router()

router.callback_query.filter(F.data.startswith(PREFIX + ":"))


@router.callback_query(F.data == MENU_MUSIC)
async def menu_music_cb(query: CallbackQuery) -> None:
    await query.answer("Пришли ссылку на трек или напиши название — найду варианты.")


@router.callback_query(F.data == MENU_VIDEO)
async def menu_video_cb(query: CallbackQuery) -> None:
    await query.answer("Пришли ссылку на видео (YouTube, Shorts, TikTok) — выберешь качество.")


@router.callback_query(F.data == MENU_FAQ)
async def menu_faq_cb(query: CallbackQuery, settings: Settings) -> None:
    await query.answer()
    if (msg := _message(query)) is not None:
        await msg.answer(
            texts.faq_text(settings),
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )


@router.callback_query(F.data == MENU_BACK)
async def menu_back_cb(query: CallbackQuery, settings: Settings) -> None:
    """«Назад» — возвращаем меню под текущим сообщением."""
    await query.answer()
    msg = _message(query)
    if msg is None:
        return
    with contextlib.suppress(Exception):
        await msg.edit_text(
            texts.welcome_text(settings),
            parse_mode="HTML",
            reply_markup=menu_inline_keyboard(),
        )


@router.callback_query(F.data == MENU_BUG)
async def menu_bug_cb(query: CallbackQuery, store: StateStore, settings: Settings) -> None:
    await query.answer()
    if query.from_user is not None:
        store.set_flag(query.from_user.id, "bugreport")
    if (msg := _message(query)) is not None:
        await msg.answer(
            f"{texts.icon(settings, 'cross')} Режим баг-репорта: опиши проблему "
            "одним сообщением — что делал, что ожидал, что получил.",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )


async def _guard(query: CallbackQuery, store: StateStore) -> tuple[list[str], DialogState | None]:
    """Проверяет права на состояние. Возвращает (parts, DialogState | None)."""
    parts = (query.data or "").split(":")
    if len(parts) < 3 or query.from_user is None:
        await query.answer("Некорректный запрос", show_alert=True)
        return parts, None
    state_id = parts[2]
    state = store.get(state_id, query.from_user.id)
    if state is None:
        await query.answer("Эта карточка устарела. Отправь ссылку заново.", show_alert=True)
        return parts, None
    return parts, state


def _message(query: CallbackQuery) -> Message | None:
    """Сообщение callback'а; None для недоступных (устаревших) сообщений."""
    msg = query.message
    if msg is None or isinstance(msg, InaccessibleMessage):
        return None
    return msg


@router.callback_query(F.data.startswith(f"{PREFIX}:type:"))
async def choose_type(query: CallbackQuery, store: StateStore, settings: Settings) -> None:
    parts, state = await _guard(query, store)
    if state is None:
        return
    kind = parts[3]
    state_id = parts[2]
    msg = _message(query)
    if msg is None:
        await query.answer("Сообщение недоступно", show_alert=True)
        return
    await msg.edit_reply_markup(
        reply_markup=options_keyboard(state_id, state.track, kind)
    )
    await query.answer()


@router.callback_query(F.data.startswith(f"{PREFIX}:back:"))
async def go_back(query: CallbackQuery, store: StateStore, settings: Settings) -> None:
    parts, state = await _guard(query, store)
    if state is None:
        return
    msg = _message(query)
    if msg is None:
        await query.answer("Сообщение недоступно", show_alert=True)
        return
    await msg.edit_reply_markup(
        reply_markup=media_type_keyboard(parts[2], state.track)
    )
    await query.answer()


@router.callback_query(F.data.startswith(f"{PREFIX}:cancel:"))
async def cancel_dialog(query: CallbackQuery, store: StateStore, settings: Settings) -> None:
    parts = (query.data or "").split(":")
    if query.from_user is not None:
        store.drop(parts[2])
    msg = _message(query)
    if msg is not None:
        with contextlib.suppress(Exception):
            await msg.edit_reply_markup(reply_markup=None)
        # Карточка может быть фото (подпись) или текстом — правим то, что есть
        try:
            await msg.edit_text(
                texts.status_line(settings, "cancelled"), parse_mode="HTML"
            )
        except Exception:
            with contextlib.suppress(Exception):
                await msg.edit_caption(
                    caption=texts.status_line(settings, "cancelled"),
                    parse_mode="HTML",
                )
    await query.answer()


@router.callback_query(F.data.startswith(f"{PREFIX}:why:"))
async def why_no_file(query: CallbackQuery, settings: Settings) -> None:
    await query.answer()
    if (msg := _message(query)) is not None:
        await msg.answer(texts.why_no_file(settings), parse_mode="HTML")


@router.callback_query(F.data.startswith(f"{PREFIX}:pick:"))
async def pick_search_result(
    query: CallbackQuery, store: StateStore, settings: Settings
) -> None:
    """Выбран результат поиска — показываем его карточку."""
    parts, state = await _guard(query, store)
    if state is None:
        return
    from app.bot.handlers.incoming import _send_cover
    from app.bot.keyboards.inline import media_type_keyboard

    await query.answer()
    msg = _message(query)
    if msg is None:
        return
    await _send_cover(
        message=msg,
        track=state.track,
        caption=texts.track_card(settings, state.track),
        reply_markup=media_type_keyboard(parts[2], state.track),
    )


@router.callback_query(F.data.startswith(f"{PREFIX}:opt:"))
async def choose_option(
    query: CallbackQuery,
    store: StateStore,
    job_queue: JobQueue,
    repo: Repository,
    settings: Settings,
) -> None:
    """Финальный выбор формата — ставим задание в очередь."""
    parts, state = await _guard(query, store)
    if state is None:
        return
    state_id, option_id = parts[2], parts[3]
    job_id = uuid.uuid4().hex[:12]
    msg = _message(query)
    if msg is None or query.from_user is None:
        await query.answer("Сообщение недоступно", show_alert=True)
        return
    option = next(
        (o for o in state.track.options if o.option_id == option_id), None
    )
    if option is None:
        await query.answer("Вариант недоступен", show_alert=True)
        return

    # Отдельное служебное сообщение для статуса: карточка с фото
    # редактируется только через edit_message_caption, поэтому статус
    # прогресса живёт в своём текстовом сообщении.
    status_msg = await msg.answer(
        texts.status_line(settings, "gear", label="Начинаю обработку...")
        + f"\n\n{_esc(state.track.title)} — {_esc(state.track.artist)}",
        parse_mode="HTML",
    )
    job = JobRequest(
        job_id=job_id,
        user_id=query.from_user.id,
        chat_id=msg.chat.id,
        status_message_id=status_msg.message_id,
        track=state.track,
        option=option,
    )
    try:
        position = await job_queue.enqueue(job)
    except MusicBotError as exc:
        await status_msg.edit_text(
            texts.status_line(settings, "error", label=str(exc)), parse_mode="HTML"
        )
        return

    await repo.create_job(
        Job(id=job_id, user_id=query.from_user.id, source=state.track.source, kind=option.kind)
    )
    store.drop(state_id)
    await msg.edit_reply_markup(reply_markup=cancel_job_keyboard(job_id, state_id))
    if position > 1:
        await status_msg.edit_text(
            texts.status_line(
                settings,
                "queued",
                label=f"Задача в очереди (позиция {position}). "
                "Пришлю файл, как только будет готово.",
            )
            + f"\n\n{_esc(state.track.title)} — {_esc(state.track.artist)}",
            parse_mode="HTML",
        )
    await query.answer("Принято!")


@router.callback_query(F.data.startswith(f"{PREFIX}:canceljob:"))
async def cancel_job(query: CallbackQuery, job_queue: JobQueue) -> None:
    parts = (query.data or "").split(":")
    job_id = parts[2]
    if query.from_user is None:
        return
    ok = await job_queue.cancel(job_id, query.from_user.id)
    msg = _message(query)
    if ok:
        await query.answer("Задание отменено", show_alert=True)
        if msg is not None:
            with contextlib.suppress(Exception):  # сообщение могло быть удалено
                await msg.edit_reply_markup(reply_markup=None)
    else:
        if msg is not None:
            # Задание уже завершилось или чужое — кнопка больше не нужна
            with contextlib.suppress(Exception):
                await msg.edit_reply_markup(reply_markup=None)
        await query.answer("Задание уже завершено или недоступно", show_alert=True)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
