"""
Модуль парсинга контактов работодателей.

Содержит компоненты для извлечения email и телефонов из:
- hh.ru API
- Официальных сайтов работодателей
"""

from .config import DEFAULT_CONFIG, SiteParserConfig
from .deduplication import deduplicate_contacts
from .exceptions import (
    RateLimitExceededError,
    SiteNotAccessibleError,
    SiteParserError,
)
from .extractors import (
    extract_emails,
    extract_phones,
    normalize_email,
    normalize_phone,
)
from .keywords import CONTACT_KEYWORDS
from .site_parser import SiteContactParser

__all__ = (
    # Конфигурация
    "SiteParserConfig",
    "DEFAULT_CONFIG",
    # Исключения
    "SiteParserError",
    "SiteNotAccessibleError",
    "RateLimitExceededError",
    # Ключевые слова
    "CONTACT_KEYWORDS",
    # Парсер
    "SiteContactParser",
    # Извлечение контактов
    "extract_emails",
    "extract_phones",
    "normalize_email",
    "normalize_phone",
    "deduplicate_contacts",
)
