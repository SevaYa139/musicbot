"""Сценарий входящего сообщения: ссылка или поисковый запрос."""

from __future__ import annotations

import contextlib
import logging
import secrets

import aiohttp
from aiogram import F, Router
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message

from app.bot import texts
from app.bot.keyboards.inline import search_results_keyboard
from app.bot.state import DialogState, StateStore
from app.config import Settings
from app.database.repository import Repository
from app.exceptions import MetadataError, MusicBotError, UnsupportedSourceError
from app.providers.base import TrackInfo
from app.providers.registry import ProviderRegistry
from app.services.search_service import SearchService
from app.utils.urls import assert_url_allowed, format_duration, is_url

log = logging.getLogger(__name__)
router = Router()

MAX_QUERY_LEN = 200


async def _send_cover(
    message: Message, track: TrackInfo, caption: str, reply_markup: InlineKeyboardMarkup
) -> None:
    """Отправляет карточку с реальной обложкой источника; fallback — текст."""
    if track.cover_url:
        try:
            async with aiohttp.ClientSession() as session, session.get(
                track.cover_url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if 0 < len(data) < 10 * 1024 * 1024:
                        await message.answer_photo(
                            BufferedInputFile(data, filename="cover.jpg"),
                            caption=caption,
                            reply_markup=reply_markup,
                            parse_mode="HTML",
                        )
                        return
        except (aiohttp.ClientError, TimeoutError):
            log.debug("Обложка недоступна, отправляю текстом")
    await message.answer(caption, reply_markup=reply_markup, parse_mode="HTML")


@router.message(F.text, ~F.text.startswith("/"))
async def handle_text(
    message: Message,
    settings: Settings,
    registry: ProviderRegistry,
    store: StateStore,
    search_service: SearchService,
    repo: Repository,
) -> None:
    user = message.from_user
    if message.text is None or user is None:
        return
    text = message.text.strip()
    await repo.touch_user(user.id)

    if store.get_flag(user.id) == "bugreport":
        await _handle_bugreport(message, text, settings, store, repo)
        return

    if is_url(text):
        await _handle_link(message, text, settings, registry, store, repo)
    else:
        await _handle_search_query(message, text, settings, search_service, store, repo)


async def _handle_bugreport(
    message: Message,
    text: str,
    settings: Settings,
    store: StateStore,
    repo: Repository,
) -> None:
    """Принимает текст баг-репорта: логирует и пересылает админам."""
    user = message.from_user
    if user is None:
        return
    store.drop_flag(user.id)
    header = f"Bug report от {user.full_name} (@{user.username or 'нет'}, id {user.id}):"
    await repo.log_error(f"{header}\n{text}"[:500], source="bugreport")
    bot = message.bot
    if bot is not None:
        for admin_id in settings.admin_ids:
            with contextlib.suppress(Exception):
                await bot.send_message(
                    admin_id,
                    f"🐞 <b>Баг-репорт</b>\n{header}\n\n{texts._esc(text)[:3000]}",
                    parse_mode="HTML",
                )
    await message.answer(
        f"{texts.icon(settings, 'check')} Спасибо! Репорт отправлен разработчику.",
        parse_mode="HTML",
    )


async def _handle_link(
    message: Message,
    url: str,
    settings: Settings,
    registry: ProviderRegistry,
    store: StateStore,
    repo: Repository,
) -> None:
    status = await message.answer(
        texts.status_line(settings, "search"), parse_mode="HTML"
    )
    try:
        safe_url = assert_url_allowed(url)
        provider = registry.resolve(safe_url)
        track = await provider.get_metadata(safe_url)
    except UnsupportedSourceError as exc:
        await status.edit_text(texts.status_line(settings, "error", label=str(exc)))
        return
    except MetadataError as exc:
        await status.edit_text(texts.status_line(settings, "error", label=str(exc)))
        await repo.log_error(str(exc), source="detect")
        return
    except MusicBotError as exc:
        await status.edit_text(texts.status_line(settings, "error", label=str(exc)))
        return
    except Exception as exc:
        log.exception("Ошибка обработки ссылки")
        await status.edit_text(
            texts.status_line(
                settings, "error", label="Не удалось обработать ссылку. Попробуйте ещё раз."
            )
        )
        await repo.log_error(type(exc).__name__, source="detect")
        return

    state_id = secrets.token_urlsafe(8)
    user = message.from_user
    if user is None:
        return
    store.set(state_id, DialogState(track=track, user_id=user.id))
    with contextlib.suppress(Exception):
        await status.delete()
    caption = texts.track_card(settings, track)
    from app.bot.keyboards.inline import media_type_keyboard

    await _send_cover(
        message=message,
        track=track,
        caption=caption,
        reply_markup=media_type_keyboard(state_id, track),
    )


async def _handle_search_query(
    message: Message,
    query: str,
    settings: Settings,
    search_service: SearchService,
    store: StateStore,
    repo: Repository,
) -> None:
    query = query[:MAX_QUERY_LEN]
    status = await message.answer(
        f"{texts.status_line(settings, 'search', label='Ищу')}: "
        f"<b>{texts._esc(query)}</b>...",
        parse_mode="HTML",
    )
    try:
        results = await search_service.search(query, per_source=3)
    except MusicBotError as exc:
        await status.edit_text(texts.status_line(settings, "error", label=str(exc)))
        return
    if not results:
        await status.edit_text(
            texts.status_line(
                settings, "error", label="Ничего не нашёл. Уточни название или пришли ссылку."
            )
        )
        return

    MAX_MESSAGE_LEN = 3500  # лимит Telegram 4096, оставляем запас
    state_ids: list[tuple[str, TrackInfo]] = []
    lines: list[str] = [
        f"{texts.status_line(settings, 'search', label='Поиск')}: <b>{texts._esc(query)}</b>\n"
    ]
    user = message.from_user
    if user is None:
        return
    for idx, track in enumerate(results[:8], start=1):
        state_id = secrets.token_urlsafe(8)
        store.set(state_id, DialogState(track=track, user_id=user.id))
        state_ids.append((state_id, track))
        kind_icon = texts.icon(settings, "video" if track.source == "tiktok" else "music")
        line = (
            f"{idx}. {kind_icon} {texts._esc(track.artist)} — {texts._esc(track.title)} "
            f"({texts.SOURCE_NAMES.get(track.source, track.source)}, "
            f"{format_duration(track.duration)})"
        )
        if sum(len(existing) for existing in lines) + len(line) > MAX_MESSAGE_LEN:
            break
        lines.append(line)
    with contextlib.suppress(Exception):
        await status.delete()
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=search_results_keyboard(state_ids),
    )
