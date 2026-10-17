"""Иерархия исключений проекта.

Сервисный слой кидает доменные исключения, хендлеры превращают их
в понятные сообщения пользователю. Никаких голых except Exception в бизнес-логике.
"""


class MusicBotError(Exception):
    """Базовое исключение проекта."""


# --- Источники и метаданные ---
class UnsupportedSourceError(MusicBotError):
    """Ссылка не распознана ни одним адаптером."""


class MetadataError(MusicBotError):
    """Не удалось получить метаданные (видео удалено, приватное, сеть)."""


class ContentUnavailableError(MusicBotError):
    """Контент существует, но скачивание запрещено владельцем / платформой."""


class SearchError(MusicBotError):
    """Ошибка поиска по названию."""


# --- Загрузка и обработка ---
class DownloadError(MusicBotError):
    """Сбой скачивания медиа."""


class ConversionError(MusicBotError):
    """Сбой обработки FFmpeg."""


class FFmpegNotFoundError(ConversionError):
    """FFmpeg/FFprobe не установлен или недоступен."""


# --- Лимиты и очередь ---
class LimitExceededError(MusicBotError):
    """Превышен лимит размера/длительности/частоты запросов."""


class JobNotFoundError(MusicBotError):
    """Задание не найдено или уже завершено."""


class JobCancelledError(MusicBotError):
    """Задание отменено пользователем или по тайм-ауту."""


class QueueFullError(MusicBotError):
    """Очередь переполнена — попробуйте позже."""


class SecurityError(MusicBotError):
    """Заблокирована потенциально небезопасная ссылка (SSRF и т.п.)."""
