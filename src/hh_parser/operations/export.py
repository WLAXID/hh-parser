from __future__ import annotations

import csv
import json
import logging
from typing import TYPE_CHECKING, Iterator, List

from ..storage.models.employer import EmployerModel

if TYPE_CHECKING:
    from ..main import HHParserTool

logger = logging.getLogger(__name__)


class Operation:
    """Экспорт данных о работодателях"""

    def run(self, tool: "HHParserTool", args) -> int | None:
        logger.info("Начало экспорта данных о работодателях")
        storage = tool.storage

        # Формируем фильтры для поиска в БД
        filters = {}
        if args.industry:
            filters["industry"] = args.industry
        if args.area:
            filters["area_name"] = args.area
        if args.min_vacancies > 0:
            filters["open_vacancies__gte"] = args.min_vacancies

        employers: Iterator[EmployerModel] = storage.employers.find()

        employers_list = list(employers)
        logger.info(f"Получено {len(employers_list)} работодателей из БД")

        # Фильтрация в памяти
        if args.industry:
            employers_list = [
                e
                for e in employers_list
                if e.industries and args.industry in e.industries
            ]
        if args.area:
            employers_list = [
                e
                for e in employers_list
                if e.area_name and args.area.lower() in e.area_name.lower()
            ]
        if args.min_vacancies > 0:
            employers_list = [
                e for e in employers_list if e.open_vacancies >= args.min_vacancies
            ]

        logger.info(f"После фильтрации осталось {len(employers_list)} работодателей")

        # Экспорт в выбранном формате
        if args.format == "csv":
            self._export_csv(employers_list, args.output)
        elif args.format == "json":
            self._export_json(employers_list, args.output)

        logger.info(f"Экспорт завершен. Данные сохранены в {args.output}")
        return 0

    def _export_csv(self, employers: List[EmployerModel], output_path: str) -> None:
        with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "id",
                "name",
                "site_url",
                "alternate_url",
                "open_vacancies",
                "total_responses",
                "avg_responses",
                "industries",
                "area_name",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for emp in employers:
                writer.writerow(
                    {
                        "id": emp.id,
                        "name": emp.name,
                        "site_url": emp.site_url or "",
                        "alternate_url": emp.alternate_url or "",
                        "open_vacancies": emp.open_vacancies,
                        "total_responses": emp.total_responses,
                        "avg_responses": emp.avg_responses,
                        "industries": emp.industries or "",
                        "area_name": emp.area_name or "",
                    }
                )

    def _export_json(self, employers: List[EmployerModel], output_path: str) -> None:
        data = []
        for emp in employers:
            data.append(
                {
                    "id": emp.id,
                    "name": emp.name,
                    "site_url": emp.site_url,
                    "alternate_url": emp.alternate_url,
                    "open_vacancies": emp.open_vacancies,
                    "total_responses": emp.total_responses,
                    "avg_responses": emp.avg_responses,
                    "industries": emp.industries,
                    "area_name": emp.area_name,
                }
            )
        with open(output_path, "w", encoding="utf-8") as jsonfile:
            json.dump(data, jsonfile, indent=2, ensure_ascii=False)
