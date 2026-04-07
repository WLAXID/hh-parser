"""
Операции экспорта данных.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hh_parser.main import HHParserTool
    from hh_parser.storage.models.contact import ContactModel
    from hh_parser.storage.models.employer import EmployerModel

logger = logging.getLogger(__name__)


class ExportEmployersOperation:
    """Экспорт работодателей в CSV или JSON."""

    def __init__(self, tool: "HHParserTool"):
        self.tool = tool
        self.storage = tool.storage

    def run(
        self,
        format: str,
        output: Path,
        area: str | None = None,
        min_vacancies: int = 0,
    ) -> dict:
        """
        Выполнить экспорт работодателей.

        Args:
            format: Формат экспорта (csv/json)
            output: Путь к выходному файлу
            area: Фильтр по региону
            min_vacancies: Минимальное количество вакансий

        Returns:
            Словарь со статистикой экспорта
        """
        # Получаем работодателей из БД
        employers_list = list(self.storage.employers.find())

        # Применяем фильтры
        if area:
            employers_list = [
                e
                for e in employers_list
                if e.area_name and area.lower() in e.area_name.lower()
            ]

        if min_vacancies > 0:
            employers_list = [
                e for e in employers_list if e.open_vacancies >= min_vacancies
            ]

        if not employers_list:
            return {"count": 0, "size": 0}

        # Экспорт
        if format == "csv":
            self._export_csv(employers_list, output)
        else:
            self._export_json(employers_list, output)

        return {
            "count": len(employers_list),
            "size": output.stat().st_size,
        }

    def _export_csv(self, employers: list["EmployerModel"], output: Path) -> None:
        """Экспорт в CSV формат."""
        with open(output, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Заголовки
            writer.writerow(
                [
                    "id",
                    "name",
                    "site_url",
                    "alternate_url",
                    "open_vacancies",
                    "industries",
                    "area_name",
                    "avg_responses",
                    "created_at",
                    "updated_at",
                ]
            )
            # Данные
            for emp in employers:
                writer.writerow(
                    [
                        emp.id,
                        emp.name,
                        emp.site_url or "",
                        emp.alternate_url or "",
                        emp.open_vacancies,
                        emp.industries or "",
                        emp.area_name or "",
                        emp.avg_responses or "",
                        emp.created_at or "",
                        emp.updated_at or "",
                    ]
                )

    def _export_json(self, employers: list["EmployerModel"], output: Path) -> None:
        """Экспорт в JSON формат."""
        data = []
        for emp in employers:
            data.append(
                {
                    "id": emp.id,
                    "name": emp.name,
                    "site_url": emp.site_url,
                    "alternate_url": emp.alternate_url,
                    "open_vacancies": emp.open_vacancies,
                    "industries": emp.industries,
                    "area_name": emp.area_name,
                    "avg_responses": emp.avg_responses,
                    "created_at": str(emp.created_at) if emp.created_at else None,
                    "updated_at": str(emp.updated_at) if emp.updated_at else None,
                }
            )

        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


class ExportContactsOperation:
    """Экспорт контактов в CSV или JSON."""

    def __init__(self, tool: "HHParserTool"):
        self.tool = tool
        self.storage = tool.storage

    def run(
        self,
        format: str,
        output: Path,
        employer_id: int | None = None,
    ) -> dict:
        """
        Выполнить экспорт контактов.

        Args:
            format: Формат экспорта (csv/json)
            output: Путь к выходному файлу
            employer_id: Фильтр по ID работодателя

        Returns:
            Словарь со статистикой экспорта
        """
        # Получаем контакты
        contacts_list = list(self.storage.contacts.find())

        if employer_id:
            contacts_list = [c for c in contacts_list if c.employer_id == employer_id]

        if not contacts_list:
            return {"count": 0, "size": 0}

        # Экспорт
        if format == "csv":
            self._export_csv(contacts_list, output)
        else:
            self._export_json(contacts_list, output)

        return {
            "count": len(contacts_list),
            "size": output.stat().st_size,
        }

    def _export_csv(self, contacts: list["ContactModel"], output: Path) -> None:
        """Экспорт в CSV формат."""
        with open(output, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "employer_id",
                    "employer_name",
                    "contact_type",
                    "value",
                    "normalized_value",
                    "source",
                    "created_at",
                ]
            )
            for contact in contacts:
                employer = self.storage.employers.get(contact.employer_id)
                employer_name = employer.name if employer else ""
                writer.writerow(
                    [
                        contact.id,
                        contact.employer_id,
                        employer_name,
                        contact.contact_type or "",
                        contact.value or "",
                        contact.normalized_value or "",
                        contact.source or "",
                        str(contact.created_at) if contact.created_at else "",
                    ]
                )

    def _export_json(self, contacts: list["ContactModel"], output: Path) -> None:
        """Экспорт в JSON формат."""
        data = []
        for contact in contacts:
            employer = self.storage.employers.get(contact.employer_id)
            data.append(
                {
                    "id": contact.id,
                    "employer_id": contact.employer_id,
                    "employer_name": employer.name if employer else None,
                    "contact_type": contact.contact_type,
                    "value": contact.value,
                    "normalized_value": contact.normalized_value,
                    "source": contact.source,
                    "created_at": str(contact.created_at)
                    if contact.created_at
                    else None,
                }
            )

        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


__all__ = (
    "ExportEmployersOperation",
    "ExportContactsOperation",
)
