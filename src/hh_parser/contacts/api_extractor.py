"""
Модуль извлечения контактов из hh.ru API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator

from hh_parser.api.errors import ResourceNotFound
from hh_parser.storage.models.contact import ContactModel

from .extractors import extract_emails, extract_phones, normalize_email, normalize_phone

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
        2. Вакансии работодателя (contacts в вакансиях)
        3. Менеджеры работодателя

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя

        Yields:
            Найденные контакты
        """
        # 1. Получаем информацию о работодателе
        try:
            employer_info = self.api_client.request("GET", f"employers/{employer_id}")
            # Получаем название работодателя из ответа API
            actual_name = employer_info.get("name", employer_name)
            yield from self._extract_from_employer_info(
                employer_id, actual_name, employer_info
            )
        except Exception as e:
            logger.warning(
                f"Ошибка получения информации о работодателе {employer_id}: {e}"
            )

        # 2. Получаем вакансии работодателя
        try:
            yield from self._extract_from_vacancies(employer_id, employer_name)
        except Exception as e:
            logger.warning(f"Ошибка получения вакансий работодателя {employer_id}: {e}")

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

    def _extract_from_vacancies(
        self, employer_id: int, employer_name: str
    ) -> Iterator[ContactModel]:
        """
        Извлечь контакты из вакансий работодателя.

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя

        Yields:
            Найденные контакты
        """
        page = 0
        per_page = 100

        while True:
            try:
                logger.debug(
                    f"[API] Запрос вакансий работодателя {employer_id}, страница {page}"
                )
                response = self.api_client.request(
                    "GET",
                    f"employers/{employer_id}/vacancies",
                    params={"page": page, "per_page": per_page},
                )

                items = response.get("items", [])
                if not items:
                    logger.debug(f"[API] Нет вакансий у работодателя {employer_id}")
                    break

                logger.debug(f"[API] Получено {len(items)} вакансий на странице {page}")

                for vacancy in items:
                    vacancy_id = vacancy.get("id", "")
                    vacancy_url = f"https://hh.ru/vacancy/{vacancy_id}"

                    # Извлекаем контакты из вакансии
                    contacts = vacancy.get("contacts", {})
                    if contacts:
                        yield from self._extract_from_vacancy_contacts(
                            employer_id=employer_id,
                            employer_name=employer_name,
                            contacts=contacts,
                            source_url=vacancy_url,
                        )

                    # Также извлекаем из описания вакансии
                    description = vacancy.get("description", "")
                    if description:
                        yield from self._extract_from_text(
                            employer_id=employer_id,
                            employer_name=employer_name,
                            text=description,
                            source_url=vacancy_url,
                        )

                # Проверяем, есть ли следующая страница
                pages = response.get("pages", 0)
                page += 1
                if page >= pages:
                    break

            except ResourceNotFound:
                # Нормальная ситуация - у работодателя нет вакансий
                logger.debug(
                    f"[API] Вакансии не найдены для работодателя {employer_id}"
                )
                break
            except Exception as e:
                logger.warning(
                    f"[API] Ошибка получения вакансий на странице {page}: {type(e).__name__}: {e}"
                )
                break

    def _extract_from_vacancy_contacts(
        self, employer_id: int, employer_name: str, contacts: dict, source_url: str
    ) -> Iterator[ContactModel]:
        """
        Извлечь контакты из поля contacts вакансии.

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя
            contacts: Словарь контактов из вакансии
            source_url: URL источника

        Yields:
            Найденные контакты
        """
        # Email
        email = contacts.get("email")
        if email:
            yield ContactModel(
                employer_id=employer_id,
                employer_name=employer_name,
                contact_type="email",
                value=email,
                source="api",
                source_url=source_url,
                normalized_value=normalize_email(email),
            )

        # Телефоны
        phones = contacts.get("phones", [])
        for phone_data in phones:
            if isinstance(phone_data, dict):
                # Телефон в формате {"city": "495", "number": "1234567", "country": "7"}
                country = phone_data.get("country", "7")
                city = phone_data.get("city", "")
                number = phone_data.get("number", "")
                if city and number:
                    phone = f"+{country} ({city}) {number}"
                else:
                    phone = phone_data.get("formatted", "")

                if phone:
                    yield ContactModel(
                        employer_id=employer_id,
                        employer_name=employer_name,
                        contact_type="phone",
                        value=phone,
                        source="api",
                        source_url=source_url,
                        normalized_value=normalize_phone(phone),
                    )
            elif isinstance(phone_data, str):
                yield ContactModel(
                    employer_id=employer_id,
                    employer_name=employer_name,
                    contact_type="phone",
                    value=phone_data,
                    source="api",
                    source_url=source_url,
                    normalized_value=normalize_phone(phone_data),
                )

    def _extract_from_text(
        self, employer_id: int, employer_name: str, text: str, source_url: str
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
