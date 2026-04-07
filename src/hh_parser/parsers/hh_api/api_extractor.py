"""
Модуль извлечения контактов из hh.ru API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator

from hh_parser.api.errors import ResourceNotFound
from hh_parser.storage.models.contact import ContactModel

from ..extractors import (
    extract_emails,
    extract_phones,
    normalize_email,
    normalize_phone,
)

if TYPE_CHECKING:
    from hh_parser.api.client import ApiClient

logger = logging.getLogger(__name__)


class ApiContactExtractor:
    """Извлечение контактов из hh.ru API."""

    def __init__(self, api_client: "ApiClient"):
        """
        Инициализировать экстрактор.

        Args:
            api_client: Клиент hh.ru API
        """
        self.api_client = api_client

    def extract_from_employer(
        self, employer_id: int, employer_name: str = ""
    ) -> Iterator[ContactModel]:
        """
        Извлечь контакты работодателя через API.

        Источники:
        1. Описание компании (description)
        2. Брендовое описание (branded_description)

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя

        Yields:
            Найденные контакты
        """
        # Получаем информацию о работодателе
        try:
            logger.debug(f"GET https://api.hh.ru/employers/{employer_id}")
            employer_info = self.api_client.request("GET", f"employers/{employer_id}")

            # Получаем название работодателя из ответа API
            actual_name = employer_info.get("name", employer_name)

            yield from self._extract_from_employer_info(
                employer_id, actual_name, employer_info
            )
        except ResourceNotFound:
            logger.debug(f"GET https://api.hh.ru/employers/{employer_id} -> 404")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.warning(
                f"Ошибка получения информации о работодателе {employer_id}: {e}"
            )

    def _extract_from_employer_info(
        self, employer_id: int, employer_name: str, employer_info: dict
    ) -> Iterator[ContactModel]:
        """
        Извлечь контакты из информации о работодателе.

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя
            employer_info: Данные о работодателе из API

        Yields:
            Найденные контакты
        """
        # Извлекаем из описания
        description = employer_info.get("description", "")
        if description:
            source_url = employer_info.get("alternate_url", "")
            yield from self._extract_from_text(
                employer_id=employer_id,
                employer_name=employer_name,
                text=description,
                source_url=source_url,
            )

        # Извлекаем из branded_description если есть
        branded_description = employer_info.get("branded_description", "")
        if branded_description:
            source_url = employer_info.get("alternate_url", "")
            yield from self._extract_from_text(
                employer_id=employer_id,
                employer_name=employer_name,
                text=branded_description,
                source_url=source_url,
            )

    def _extract_from_text(
        self,
        employer_id: int,
        employer_name: str,
        text: str,
        source_url: str,
    ) -> Iterator[ContactModel]:
        """
        Извлечь контакты из произвольного текста.

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя
            text: Текст для поиска
            source_url: URL источника

        Yields:
            Найденные контакты
        """
        # Извлекаем email
        for email in extract_emails(text):
            yield ContactModel(
                employer_id=employer_id,
                employer_name=employer_name,
                contact_type="email",
                value=email,
                source="api",
                source_url=source_url,
                normalized_value=normalize_email(email),
            )

        # Извлекаем телефоны
        for phone in extract_phones(text):
            yield ContactModel(
                employer_id=employer_id,
                employer_name=employer_name,
                contact_type="phone",
                value=phone,
                source="api",
                source_url=source_url,
                normalized_value=normalize_phone(phone),
            )


__all__ = ("ApiContactExtractor",)
