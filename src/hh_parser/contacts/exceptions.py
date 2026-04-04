"""Исключения для парсера сайта работодателя."""


class SiteParserError(Exception):
    """Базовая ошибка парсера сайта."""

    pass


class SiteNotAccessibleError(SiteParserError):
    """Сайт недоступен."""

    pass


class RateLimitExceededError(SiteParserError):
    """Превышен лимит запросов."""

    pass


__all__ = (
    "SiteParserError",
    "SiteNotAccessibleError",
    "RateLimitExceededError",
)
