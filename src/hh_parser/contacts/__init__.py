"""
Модуль парсинга контактов работодателей.

Содержит компоненты для извлечения email и телефонов из:
- hh.ru API
- Официальных сайтов работодателей
"""

from .deduplication import deduplicate_contacts
from .extractors import (
    extract_emails,
    extract_phones,
    normalize_email,
    normalize_phone,
)

__all__ = (
    "extract_emails",
    "extract_phones",
    "normalize_email",
    "normalize_phone",
    "deduplicate_contacts",
)
