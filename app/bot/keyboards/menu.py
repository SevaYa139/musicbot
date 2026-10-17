"""Инлайн-меню под сообщениями (кнопки, а не клавиатура ввода)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.inline import PREFIX, _btn_icon

MENU_MUSIC = f"{PREFIX}:menu:music"
MENU_VIDEO = f"{PREFIX}:menu:video"
MENU_FAQ = f"{PREFIX}:menu:faq"
MENU_BUG = f"{PREFIX}:menu:bug"
MENU_BACK = f"{PREFIX}:menu:back"

_BACK = InlineKeyboardButton(text="◀️ Назад", callback_data=MENU_BACK)


def menu_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Музыка", callback_data=MENU_MUSIC, **_btn_icon("music")
                ),
                InlineKeyboardButton(
                    text="Видео", callback_data=MENU_VIDEO, **_btn_icon("video")
                ),
            ],
            [
                InlineKeyboardButton(
                    text="FAQ", callback_data=MENU_FAQ, **_btn_icon("search")
                ),
                InlineKeyboardButton(
                    text="Сообщить о баге", callback_data=MENU_BUG, **_btn_icon("cross")
                ),
            ],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    """Меню из одной кнопки «Назад» — для вложенных экранов (FAQ, баг)."""
    return InlineKeyboardMarkup(inline_keyboard=[[_BACK]])
