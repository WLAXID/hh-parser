"""
CLI-команда для парсинга контактов работодателей.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator

from hh_parser.cli.config import ParseContactsConfig, SiteParserConfig
from hh_parser.parsers.deduplication import deduplicate_contacts
from hh_parser.parsers.employer_sites.site_parser import SiteContactParser
from hh_parser.parsers.hh_api.api_extractor import ApiContactExtractor
from hh_parser.storage.models.contact import ContactModel
from hh_parser.storage.models.employer import EmployerModel

if TYPE_CHECKING:
    from hh_parser.main import HHParserTool

logger = logging.getLogger(__name__)


class Operation:
    """Парсинг контактов работодателей."""

    def run(self, tool: "HHParserTool", args) -> int | None:
        logger.info("Начало парсинга контактов работодателей")

        # Загружаем конфигурацию из файла
        config_data = tool.config.get("parse_contacts", {})
        file_config = ParseContactsConfig.from_dict(config_data)

        site_config_data = tool.config.get("site_parser", {})
        file_site_config = SiteParserConfig.from_dict(site_config_data)

        # Определяем итоговые значения: приоритет у аргументов CLI, затем конфиг из файла
        final_source = getattr(args, "source", None) or file_config.source
        final_site_timeout = (
            getattr(args, "site_timeout", None) or file_config.site_timeout
        )
        final_max_pages = getattr(args, "max_pages", None) or file_config.max_pages
        final_delay = getattr(args, "delay", None) or file_config.delay

        # Получаем список работодателей для обработки
        employers = self._get_employers(tool, args)
        employers_list = list(employers)

        if not employers_list:
            logger.info("Нет работодателей для обработки")
            return 0

        logger.info(f"Найдено {len(employers_list)} работодателей для обработки")

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

        if final_source in ("api", "both"):
            api_extractor = ApiContactExtractor(tool.api_client)

        if final_source in ("site", "both"):
            site_config = SiteParserConfig(
                timeout=file_site_config.timeout,
                connect_timeout=final_site_timeout,
                max_pages_per_site=final_max_pages,
                delay_between_requests=final_delay,
                max_redirects=file_site_config.max_redirects,
                user_agent=file_site_config.user_agent,
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
                    source=final_source,
                )

                # Дедуплицируем и сохраняем
                unique_contacts = deduplicate_contacts(contacts)
                saved = tool.storage.contacts.save_many(unique_contacts)

                # Обновляем статус контактов работодателя
                if len(unique_contacts) == 0:
                    # Контакты не найдены
                    employer.contacts_status = "no_contacts"
                else:
                    # Контакты найдены
                    employer.contacts_status = "has_contacts"

                tool.storage.employers.save(employer)

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
                    f"{employer.id} {employer.site_url} -> email:{emails_count} phone:{phones_count} status:{employer.contacts_status}"
                )

            except KeyboardInterrupt:
                raise
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

        Фильтрует по contacts_status - обрабатывает только тех, у кого статус:
        - None (не установлен)
        - '' (пустая строка)
        - 'not_checked' (требует проверки)

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
            # Все работодатели с site_url и без статуса контактов
            query = tool.storage.employers.find()
            for employer in query:
                # Пропускаем если уже обработан (не None и не 'not_checked')
                if (
                    employer.contacts_status
                    and employer.contacts_status != "not_checked"
                ):
                    continue

                # Пропускаем если нет site_url
                if not employer.site_url:
                    continue

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
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.warning(f"Ошибка извлечения из API для {employer.id}: {e}")

        # Парсим сайт
        if site_parser and source in ("site", "both") and employer.site_url:
            try:
                for contact in site_parser.parse_site(
                    employer.id, employer.name, employer.site_url
                ):
                    contacts.append(contact)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.warning(f"Ошибка парсинга сайта для {employer.id}: {e}")

        return contacts
