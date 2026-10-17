"""Команды /start, /help, /limits, FAQ и админка (/stats, /queue)."""

from __future__ import annotations

import contextlib
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message, ReplyKeyboardRemove

from app.bot import texts
from app.bot.filters.admin import IsAdmin
from app.bot.keyboards.menu import back_keyboard, menu_inline_keyboard
from app.config import Settings
from app.database.repository import Repository
from app.jobqueue.base import JobQueue

router = Router()

WELCOME_IMAGE = Path(__file__).resolve().parents[3] / "assets" / "welcome.jpg"


@router.message(Command("start"))
async def start(message: Message, settings: Settings) -> None:
    if WELCOME_IMAGE.exists():
        await message.answer_photo(
            FSInputFile(WELCOME_IMAGE),
            caption=texts.welcome_text(settings),
            parse_mode="HTML",
            reply_markup=menu_inline_keyboard(),
        )
    else:
        await message.answer(
            texts.welcome_text(settings),
            parse_mode="HTML",
            reply_markup=menu_inline_keyboard(),
        )
    # Тихо убираем старую reply-клавиатуру, если она ещё показывается:
    # невидимое сообщение (zero-width space) + удаление сразу
    with contextlib.suppress(Exception):
        notice = await message.answer("​", reply_markup=ReplyKeyboardRemove())
        await notice.delete()


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(
        "Пришли ссылку на трек или видео — подготовлю варианты форматов.\n"
        "Или напиши название — найду среди поддерживаемых источников.\n\n"
        "Команды: /start, /limits, /faq",
        parse_mode="HTML",
    )


@router.message(Command("limits"))
async def limits(message: Message, settings: Settings) -> None:
    await message.answer(texts.about_limits(settings), parse_mode="HTML")


@router.message(Command("faq"))
@router.message(F.text == "FAQ")
async def faq(message: Message, settings: Settings) -> None:
    await message.answer(
        texts.faq_text(settings),
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )


# --- Администрирование: строго по ADMIN_IDS ---

@router.message(Command("stats"), IsAdmin())
async def stats(message: Message, settings: Settings, repo: Repository) -> None:
    data = await repo.stats()
    by_source = "\n".join(
        f"  • {src}: {count}" for src, count in sorted(data["by_source"].items())
    ) or "  • нет данных"
    avg = f"{data['avg_seconds']} сек" if data["avg_seconds"] else "—"
    await message.answer(
        f"{texts.icon(settings, 'chart')} <b>Статистика</b>\n\n"
        f"Пользователей: {data['users']} (активных за 24ч: {data['active_24h']})\n"
        f"Успешных загрузок: {data['done_jobs']}\n"
        f"Ошибок: {data['failed_jobs']}\n"
        f"Среднее время обработки: {avg}\n\n"
        f"По источникам:\n{by_source}",
        parse_mode="HTML",
    )


@router.message(Command("queue"), IsAdmin())
async def queue_info(message: Message, settings: Settings, job_queue: JobQueue) -> None:
    size = await job_queue.size()
    await message.answer(
        f"{texts.icon(settings, 'inbox')} Заданий в очереди: {size}", parse_mode="HTML"
    )
