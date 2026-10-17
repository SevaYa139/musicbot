"""Единый визуальный стиль текстовых карточек и статусов.

Кастомные эмодзи из пакета tgiosicons подставляются через <tg-emoji>,
если заданы их document id в конфиге; иначе — обычные эмодзи.
"""

from __future__ import annotations

from app.config import Settings
from app.providers.base import TrackInfo
from app.utils.urls import format_duration

SOURCE_NAMES = {
    "youtube": "YouTube",
    "soundcloud": "SoundCloud",
    "spotify": "Spotify",
    "yandex": "Яндекс Музыка",
    "tiktok": "TikTok",
}


def _e(custom: str | None, fallback: str) -> str:
    """Кастомный эмодзи из пакета, если задан его document id, иначе обычный."""
    if custom and custom.isdigit():
        return f'<tg-emoji emoji-id="{custom}">{fallback}</tg-emoji>'
    return fallback


def _icons(settings: Settings) -> dict[str, str]:
    """Единая карта иконок: кастомные при наличии, иначе fallback."""
    return {
        "music": _e(settings.custom_emoji_music, "🎵"),
        "video": _e(settings.custom_emoji_video, "🎬"),
        "download": _e(settings.custom_emoji_download, "⬇️"),
        "search": _e(settings.custom_emoji_search, "🔎"),
        "gear": _e(settings.custom_emoji_gear, "⚙️"),
        "upload": _e(settings.custom_emoji_upload, "📤"),
        "inbox": _e(settings.custom_emoji_inbox, "📥"),
        "check": _e(settings.custom_emoji_check, "✅"),
        "cross": _e(settings.custom_emoji_cross, "❌"),
        "chart": _e(settings.custom_emoji_chart, "📊"),
        "link": _e(settings.custom_emoji_link, "🔗"),
        "play": _e(settings.custom_emoji_play, "▶️"),
        "timer": "⏱",
    }


def icon(settings: Settings, key: str) -> str:
    """Одна иконка из карты (music/video/search/...) — кастомная или fallback."""
    return _icons(settings).get(key, "▫️")


def track_card(settings: Settings, track: TrackInfo) -> str:
    """Карточка трека/видео: название, автор, длительность, источник."""
    icons = _icons(settings)
    lines = [
        f"<b>{_esc(track.title)}</b>",
        f"{_esc(track.artist)}",
        "",
        f"{icons['timer']} {format_duration(track.duration)}   •   "
        f"{SOURCE_NAMES.get(track.source, track.source)}",
    ]
    notes = [o.note for o in track.options if o.note]
    if notes:
        lines += ["", f"<i>{_esc(notes[0])}</i>"]
    return "\n".join(lines)


def status_line(settings: Settings, key: str, percent: int = -1, label: str = "") -> str:
    """Строка статуса с иконкой; прогресс-бар только при достоверном проценте."""
    icons = _icons(settings)
    text = label or {
        "search": "Получаю информацию о файле...",
        "download": "Загружаю",
        "process": "Обрабатываю...",
        "upload": "Отправляю файл...",
        "done": "Готово!",
        "queued": "Задача в очереди",
        "cancelled": "Отменено.",
        "error": "Ошибка.",
    }.get(key, key)
    text = f"{icons.get(key, icons['gear'])} {text}"
    if percent >= 0:
        filled = percent // 10
        bar = "█" * filled + "░" * (10 - filled)
        return f"{text}\n<code>{bar}</code> {percent}%"
    return text


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def welcome_text(settings: Settings) -> str:
    """Приветственный текст с иконками пакета."""
    icons = _icons(settings)
    return (
        "<b>Просто отправь ссылку на музыку или видео.</b>\n\n"
        "Поддерживаемые источники:\n"
        f"{icons['play']} YouTube и Shorts\n"
        f"{icons['music']} SoundCloud\n"
        f"{icons['music']} Spotify\n"
        f"{icons['music']} Яндекс Музыка\n"
        f"{icons['video']} TikTok"
    )

def about_limits(settings: Settings) -> str:
    icons = _icons(settings)
    return (
        f"{icons['gear']} <b>Ограничения</b>\n\n"
        "• Максимальный размер файла — до 2 ГБ (зависит от настроек сервера)\n"
        "• Очередь: если сервер занят, задача подождёт своей очереди\n"
        "• Длительность видео — до двух часов\n\n"
        "Качество не выше исходника: конвертация в 320 kbps не делает звук лучше."
    )


def why_no_file(settings: Settings) -> str:
    return (
        "ℹ️ <b>Почему нет файла</b>\n\n"
        "Некоторые платформы (Spotify, Яндекс Музыка) не отдают аудиофайлы "
        "через открытый API. Бот показывает метаданные и ссылку на оригинал, "
        "но не обходит DRM и подписочные ограничения."
    )


def faq_text(settings: Settings) -> str:
    icons = _icons(settings)
    return (
        f"{icons['search']} <b>FAQ</b>\n\n"
        "<b>Как скачать?</b>\n"
        "Пришли ссылку → выбери аудио или видео → получи файл. "
        "Или напиши название трека — бот найдёт варианты.\n\n"
        "<b>Какие источники поддерживаются?</b>\n"
        f"{icons['play']} YouTube (включая Shorts)\n"
        f"{icons['music']} SoundCloud\n"
        f"{icons['music']} Spotify (метаданные)\n"
        f"{icons['music']} Яндекс Музыка (метаданные)\n"
        f"{icons['video']} TikTok\n\n"
        "<b>Почему нет плейлистов?</b>\n"
        "Плейлисты YouTube не поддерживаются — только отдельные треки и видео.\n\n"
        "<b>Какие ограничения?</b>\n"
        "Файлы до 2 ГБ, видео до 2 часов. Качество не выше исходника.\n\n"
        "<b>Инлайн-режим</b>\n"
        "Пиши @SaveStati_bot и название в любом чате — выберешь результат из списка.\n\n"
        "<b>Нашёл баг?</b>\n"
        "Нажми «Сообщить о баге» в меню и опиши проблему одним сообщением."
    )
