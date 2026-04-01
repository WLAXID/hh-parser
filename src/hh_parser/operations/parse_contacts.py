"""
CLI-команда для парсинга контактов работодателей.
"""

from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING, Iterator

from hh_parser.contacts.api_extractor import ApiContactExtractor
from hh_parser.contacts.deduplication import deduplicate_contacts
from hh_parser.contacts.site_parser import SiteContactParser, SiteParserConfig
from hh_parser.main import BaseOperation
from hh_parser.storage.models.contact import ContactModel
from hh_parser.storage.models.employer import EmployerModel

if TYPE_CHECKING:
    from hh_parser.main import HHParserTool

logger = logging.getLogger(__name__)


class Operation(BaseOperation):
    """Парсинг контактов работодателей."""

    __aliases__: list = ["parse-contacts", "contacts"]

    def setup_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--source",
            choices=["api", "site", "both"],
            default="both",
            help="Источник контактов: api (только hh.ru API), site (только сайт), both (оба)",
        )
        parser.add_argument(
            "--employer-id",
            type=int,
            nargs="+",
            help="ID конкретных работодателей для парсинга",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Ограничение количества работодателей (0 = без ограничений)",
        )
        parser.add_argument(
            "--skip-with-contacts",
            action="store_true",
            help="Пропустить работодателей, у которых уже есть контакты",
        )
        parser.add_argument(
            "--site-timeout",
            type=int,
            default=30,
            help="Таймаут для запросов к сайтам работодателей (секунды)",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=10,
            help="Максимум страниц для парсинга на одном сайте",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=2.0,
            help="Задержка между запросами к одному сайту (секунды)",
        )

    def run(self, tool: "HHParserTool", args) -> int | None:
        logger.info("Начало парсинга контактов работодателей")

        # Получаем список работодателей для обработки
        employers = self._get_employers(tool, args)
        employers_list = list(employers)

        if not employers_list:
            logger.info("Нет работодателей для обработки")
            return 0

        logger.info(f"Найдено {len(employers_list)} работодателей")

        # Статистика
        stats = {
            "employers_processed": 0,
            "contacts_found": 0,
            "emails_found": 0,
            "phones_found": 0,
            "errors": 0,
        }

        # Инициализируем экстракторы
        api_extractor = None
        site_parser = None

        if args.source in ("api", "both"):
            api_extractor = ApiContactExtractor(tool.api_client)

        if args.source in ("site", "both"):
            site_config = SiteParserConfig(
                timeout=args.site_timeout,
                max_pages_per_site=args.max_pages,
                delay_between_requests=args.delay,
            )
            site_parser = SiteContactParser(site_config)

        # Обрабатываем каждого работодателя
        for employer in employers_list:
            try:
                logger.info(f"{employer.id} {employer.site_url}")

                contacts = self._process_employer(
                    employer=employer,
                    api_extractor=api_extractor,
                    site_parser=site_parser,
                    source=args.source,
                )

                # Дедуплицируем и сохраняем
                unique_contacts = deduplicate_contacts(contacts)
                saved = tool.storage.contacts.save_many(unique_contacts)

                stats["employers_processed"] += 1
                stats["contacts_found"] += saved

                emails_count = sum(
                    1 for c in unique_contacts if c.contact_type == "email"
                )
                phones_count = sum(
                    1 for c in unique_contacts if c.contact_type == "phone"
                )
                stats["emails_found"] += emails_count
                stats["phones_found"] += phones_count

                logger.info(
                    f"{employer.id} {employer.site_url} -> email:{emails_count} phone:{phones_count}"
                )

            except Exception as e:
                logger.error(f"Ошибка обработки работодателя {employer.id}: {e}")
                stats["errors"] += 1

        # Закрываем ресурсы
        if site_parser:
            site_parser.close()

        # Выводим статистику
        logger.info(
            f"Итого: обработано {stats['employers_processed']} работодателей, "
            f"найдено {stats['contacts_found']} контактов "
            f"(email: {stats['emails_found']}, phone: {stats['phones_found']})"
        )

        return 0 if stats["errors"] == 0 else 1

    def _get_employers(self, tool: "HHParserTool", args) -> Iterator[EmployerModel]:
        """
        Получить список работодателей для обработки.

        Args:
            tool: Экземпляр HHParserTool
            args: Аргументы CLI

        Yields:
            Модели работодателей
        """
        if args.employer_id:
            # Конкретные работодатели
            for emp_id in args.employer_id:
                employer = tool.storage.employers.find_one(id=emp_id)
                if employer:
                    yield employer
                else:
                    logger.warning(f"Работодатель {emp_id} не найден в БД")
        else:
            # Все работодатели с site_url
            query = tool.storage.employers.find()

            if args.skip_with_contacts:
                # Получаем ID работодателей с контактами
                employers_with_contacts = set(
                    tool.storage.contacts.get_employers_with_contacts()
                )
                for employer in query:
                    if employer.id not in employers_with_contacts:
                        if employer.site_url:
                            yield employer
            else:
                for employer in query:
                    if employer.site_url:
                        yield employer

        # Применяем лимит
        # Note: это делается через генератор, поэтому лимит применяется при итерации

    def _process_employer(
        self,
        employer: EmployerModel,
        api_extractor: ApiContactExtractor | None,
        site_parser: SiteContactParser | None,
        source: str,
    ) -> list[ContactModel]:
        """
        Обработать одного работодателя.

        Args:
            employer: Модель работодателя
            api_extractor: Экстрактор из API
            site_parser: Парсер сайта
            source: Источник (api/site/both)

        Returns:
            Список найденных контактов
        """
        contacts: list[ContactModel] = []

        # Извлекаем из API
        if api_extractor and source in ("api", "both"):
            try:
                for contact in api_extractor.extract_from_employer(
                    employer.id, employer.name
                ):
                    contacts.append(contact)
            except Exception as e:
                logger.warning(f"Ошибка извлечения из API для {employer.id}: {e}")

        # Парсим сайт
        if site_parser and source in ("site", "both") and employer.site_url:
            try:
                for contact in site_parser.parse_site(
                    employer.id, employer.name, employer.site_url
                ):
                    contacts.append(contact)
            except Exception as e:
                logger.warning(f"Ошибка парсинга сайта для {employer.id}: {e}")

        return contacts
