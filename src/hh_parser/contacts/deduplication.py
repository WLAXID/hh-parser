"""
Модуль дедупликации контактов.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from hh_parser.storage.models.contact import ContactModel

from .extractors import normalize_email, normalize_phone


def deduplicate_contacts(contacts: Iterable[ContactModel]) -> list[ContactModel]:
    """
    Удалить дубликаты контактов.

    Группирует контакты по (contact_type, normalized_value) - глобально,
    и выбирает лучшее представление для каждой группы.

    Args:
        contacts: Итерируемый объект с контактами

    Returns:
        Список уникальных контактов
    """
    # Группируем по ключу (contact_type, normalized_value) - глобальная уникальность
    groups: dict[tuple, list[ContactModel]] = defaultdict(list)

    for contact in contacts:
        # Нормализуем значение если ещё не нормализовано
        if not contact.normalized_value:
            if contact.contact_type == "email":
                contact.normalized_value = normalize_email(contact.value)
            else:
                contact.normalized_value = normalize_phone(contact.value)

        key = (contact.contact_type, contact.normalized_value)
        groups[key].append(contact)

    # Выбираем лучшее представление для каждой группы
    result = []
    for key, group in groups.items():
        best = _select_best_contact(group)
        result.append(best)

    return result


def _select_best_contact(contacts: list[ContactModel]) -> ContactModel:
    """
    Выбрать лучшее представление контакта из группы дубликатов.

    Приоритеты:
    1. Контакты из API (более надёжные)
    2. Более полное представление (без обфускации)
    3. Первый в списке

    Args:
        contacts: Группа дубликатов

    Returns:
        Лучший контакт из группы
    """
    if len(contacts) == 1:
        return contacts[0]

    # Сортируем по приоритету: API > site, затем по длине значения
    def sort_key(contact: ContactModel) -> tuple:
        # Приоритет источника: api=0, site=1
        source_priority = 0 if contact.source == "api" else 1
        # Длина значения (длиннее = лучше, меньше обфускации)
        value_length = -len(contact.value)
        return (source_priority, value_length)

    sorted_contacts = sorted(contacts, key=sort_key)
    return sorted_contacts[0]


def merge_contacts(
    existing: Iterable[ContactModel], new: Iterable[ContactModel]
) -> tuple[list[ContactModel], list[ContactModel]]:
    """
    Слить новые контакты с существующими.

    Args:
        existing: Существующие контакты
        new: Новые контакты

    Returns:
    Кортеж (контакты для добавления, контакты для обновления)
    """
    existing_by_key: dict[tuple, ContactModel] = {}

    for contact in existing:
        # Глобальная уникальность по (contact_type, normalized_value)
        key = (contact.contact_type, contact.normalized_value)
        existing_by_key[key] = contact

    to_add = []
    to_update = []

    for contact in new:
        # Глобальная уникальность по (contact_type, normalized_value)
        key = (contact.contact_type, contact.normalized_value)

        if key in existing_by_key:
            # Контакт уже существует - проверяем, нужно ли обновление
            existing_contact = existing_by_key[key]
            if _should_update(existing_contact, contact):
                to_update.append(contact)
        else:
            # Новый контакт
            to_add.append(contact)

    return to_add, to_update


def _should_update(existing: ContactModel, new: ContactModel) -> bool:
    """
    Определить, нужно ли обновить существующий контакт.

    Обновляем если:
    - Новый контакт из API, а существующий с сайта
    - Новое значение более полное

    Args:
        existing: Существующий контакт
        new: Новый контакт

    Returns:
        True если нужно обновить
    """
    # API приоритетнее сайта
    if new.source == "api" and existing.source == "site":
        return True

    # Более полное представление
    if len(new.value) > len(existing.value):
        return True

    return False
