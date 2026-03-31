"""
Regex-экстракторы для извлечения email и телефонов из текста.
"""

from __future__ import annotations

import logging
import re
from typing import Iterator

logger = logging.getLogger(__name__)

# ============================================================================
# Паттерны для email
# ============================================================================

# Основной паттерн email
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)

# Паттерны для обфусцированных email
EMAIL_OBFUSCATED_PATTERNS = [
    # user at domain dot com
    re.compile(
        r"[a-zA-Z0-9._%+-]+\s*[\[\(]?\s*at\s*[\]\)]?\s*[a-zA-Z0-9.-]+\s*[\[\(]?\s*dot\s*[\]\)]?\s*[a-zA-Z]{2,}",
        re.IGNORECASE,
    ),
    # user @ domain . com (с пробелами)
    re.compile(
        r"[a-zA-Z0-9._%+-]+\s*@\s*[a-zA-Z0-9.-]+\s*\.\s*[a-zA-Z]{2,}", re.IGNORECASE
    ),
    # user [at] domain [dot] com
    re.compile(
        r"[a-zA-Z0-9._%+-]+\s*\[at\]\s*[a-zA-Z0-9.-]+\s*\[dot\]\s*[a-zA-Z]{2,}",
        re.IGNORECASE,
    ),
]

# Паттерны для исключения (не email)
EMAIL_EXCLUDE_PATTERNS = [
    re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|bmp)$", re.IGNORECASE),  # изображения
    re.compile(
        r"^(noreply|no-reply|donotreply|example|test)@", re.IGNORECASE
    ),  # автоматические
    re.compile(r"@\d+\.\d+\.\d+"),  # IP-адреса
    re.compile(r"@localhost"),  # локальные адреса
]


# ============================================================================
# Паттерны для телефонов
# ============================================================================

# Российские телефоны
PHONE_RU_PATTERNS = [
    # +7 (XXX) XXX-XX-XX
    re.compile(r"\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"),
    # 8 (XXX) XXX-XX-XX
    re.compile(r"(?<!\d)8[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"),
    # +7XXXXXXXXXX (10 цифр после +7)
    re.compile(r"\+7\d{10}"),
    # 8XXXXXXXXXX (10 цифр после 8)
    re.compile(r"(?<!\d)8\d{10}(?!\d)"),
]

# Международные телефоны
PHONE_INTL_PATTERNS = [
    # +XXX XX XXX XXXX (различные форматы)
    re.compile(
        r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,4}[\s\-]?\d{1,9}"
    ),
    # +XXXXXXXXXXX (просто цифры с плюсом)
    re.compile(r"\+\d{7,15}"),
]

# Паттерны для исключения (не телефоны)
PHONE_EXCLUDE_PATTERNS = [
    re.compile(r"^\d{1,4}$"),  # короткие числа (годы, коды)
    re.compile(r"^\d{6}$"),  # почтовые индексы
    re.compile(r"^\d{4,5}$"),  # года, короткие коды
    re.compile(r"19\d{2}|20\d{2}"),  # года 1900-2099
    re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}"),  # даты
]


def extract_emails(text: str) -> Iterator[str]:
    """
    Извлечь все email-адреса из текста.

    Args:
        text: Исходный текст для поиска

    Yields:
        Найденные email-адреса
    """
    if not text:
        return

    # Извлекаем стандартные email
    for match in EMAIL_PATTERN.finditer(text):
        email = match.group(0)
        if _is_valid_email(email):
            yield email

    # Извлекаем обфусцированные email
    for pattern in EMAIL_OBFUSCATED_PATTERNS:
        for match in pattern.finditer(text):
            obfuscated = match.group(0)
            email = _deobfuscate_email(obfuscated)
            if email and _is_valid_email(email):
                yield email


def extract_phones(text: str) -> Iterator[str]:
    """
    Извлечь все телефонные номера из текста.

    Args:
        text: Исходный текст для поиска

    Yields:
        Найденные телефонные номера
    """
    if not text:
        return

    # Извлекаем российские телефоны
    for pattern in PHONE_RU_PATTERNS:
        for match in pattern.finditer(text):
            phone = match.group(0)
            if _is_valid_phone(phone):
                yield phone

    # Извлекаем международные телефоны
    for pattern in PHONE_INTL_PATTERNS:
        for match in pattern.finditer(text):
            phone = match.group(0)
            if _is_valid_phone(phone):
                yield phone


def normalize_email(email: str) -> str:
    """
    Нормализовать email-адрес.

    Приводит к нижнему регистру и удаляет лишние пробелы.

    Args:
        email: Email-адрес

    Returns:
        Нормализованный email-адрес
    """
    return email.lower().strip()


def normalize_phone(phone: str) -> str:
    """
    Нормализовать телефонный номер.

    Приводит к формату +7XXXXXXXXXX для российских номеров
    или +XXXXXXXXXXX для международных.

    Args:
        phone: Телефонный номер

    Returns:
        Нормализованный телефонный номер
    """
    # Удаляем все кроме цифр и плюса
    digits = re.sub(r"[^\d+]", "", phone)

    # Если пусто - возвращаем как есть
    if not digits:
        return phone

    # Обработка российских номеров
    if digits.startswith("8") and len(digits) == 11:
        # 8XXXXXXXXXX -> +7XXXXXXXXXX
        digits = "+7" + digits[1:]
    elif digits.startswith("7") and len(digits) == 11:
        # 7XXXXXXXXXX -> +7XXXXXXXXXX
        digits = "+" + digits
    elif not digits.startswith("+"):
        # Добавляем плюс если его нет
        digits = "+" + digits

    return digits


def _is_valid_email(email: str) -> bool:
    """Проверить, что email валидный и не должен быть исключён."""
    email_lower = email.lower()
    for pattern in EMAIL_EXCLUDE_PATTERNS:
        if pattern.search(email_lower):
            return False
    return True


def _is_valid_phone(phone: str) -> bool:
    """Проверить, что телефон валидный и не должен быть исключён."""
    for pattern in PHONE_EXCLUDE_PATTERNS:
        if pattern.search(phone):
            return False
    return True


def _deobfuscate_email(obfuscated: str) -> str | None:
    """
    Преобразовать обфусцированный email в обычный формат.

    Args:
        obfuscated: Обфусцированный email (например, "user at domain dot com")

    Returns:
        Обычный email или None если не удалось преобразовать
    """
    # Удаляем скобки и приводим к нижнему регистру
    text = obfuscated.lower()
    text = re.sub(r"[\[\]\(\)]", "", text)

    # Заменяем "at" на "@"
    text = re.sub(r"\bat\b", "@", text)

    # Заменяем "dot" на "."
    text = re.sub(r"\bdot\b", ".", text)

    # Удаляем лишние пробелы
    text = re.sub(r"\s+", "", text)

    # Проверяем, что получился валидный email
    if EMAIL_PATTERN.fullmatch(text):
        return text

    return None
