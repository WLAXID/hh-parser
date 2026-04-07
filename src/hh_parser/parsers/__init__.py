"""
Модули парсинга данных.

Структура:
- hh_api/ — парсинг hh.ru API
- employer_sites/ — парсинг сайтов работодателей
"""

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

__all__ = (
    # Извлечение контактов
    "extract_emails",
    "extract_phones",
    "normalize_email",
    "normalize_phone",
    "deduplicate_contacts",
    # Ключевые слова
    "CONTACT_KEYWORDS",
    # Исключения
    "SiteParserError",
    "SiteNotAccessibleError",
    "RateLimitExceededError",
)
