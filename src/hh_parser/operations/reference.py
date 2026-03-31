"""Команда для вывода справочников (отрасли, регионы) из API hh.ru."""

from __future__ import annotations

import argparse
import json
import logging
from typing import TYPE_CHECKING

from ..main import BaseOperation

if TYPE_CHECKING:
    from ..main import HHParserTool

logger = logging.getLogger(__name__)


class Operation(BaseOperation):
    """Вывод справочников из API hh.ru."""

    __aliases__: list = ["reference", "ref", "dict", "dictionaries"]

    def setup_parser(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(
            dest="reference_type", help="Тип справочника"
        )

        # Подкоманда для отраслей
        industries_parser = subparsers.add_parser(
            "industries", aliases=["ind"], help="Справочник отраслей"
        )
        industries_parser.add_argument(
            "--format",
            choices=["table", "json", "simple"],
            default="table",
            help="Формат вывода: table (таблица), json, simple (простой список)",
        )
        industries_parser.add_argument(
            "--search",
            type=str,
            help="Фильтр по названию отрасли (регистронезависимый поиск)",
        )
        industries_parser.add_argument(
            "--page",
            type=int,
            default=0,
            help="Номер страницы для пагинации (начиная с 0)",
        )
        industries_parser.add_argument(
            "--per-page",
            type=int,
            default=50,
            help="Количество элементов на странице (по умолчанию 50, 0 — показать все)",
        )

        # Подкоманда для регионов
        areas_parser = subparsers.add_parser(
            "areas", aliases=["regions"], help="Справочник регионов"
        )
        areas_parser.add_argument(
            "--format",
            choices=["table", "json", "simple", "tree"],
            default="table",
            help="Формат вывода: table (таблица), json, simple (плоский список), tree (дерево)",
        )
        areas_parser.add_argument(
            "--search",
            type=str,
            help="Фильтр по названию региона (регистронезависимый поиск)",
        )
        areas_parser.add_argument(
            "--country",
            type=str,
            help="Фильтр по стране (ID или название)",
        )
        areas_parser.add_argument(
            "--max-depth",
            type=int,
            default=3,
            help="Максимальная глубина вложенности для дерева (по умолчанию 3)",
        )
        areas_parser.add_argument(
            "--page",
            type=int,
            default=0,
            help="Номер страницы для пагинации (начиная с 0)",
        )
        areas_parser.add_argument(
            "--per-page",
            type=int,
            default=50,
            help="Количество элементов на странице (по умолчанию 50, 0 — показать все)",
        )

    def run(self, tool: "HHParserTool", args) -> int | None:
        if not args.reference_type:
            logger.error(
                "Не указан тип справочника. Используйте 'industries' или 'areas'"
            )
            return 1

        api_client = tool.api_client

        if args.reference_type in ["industries", "ind"]:
            return self._show_industries(api_client, args)
        elif args.reference_type in ["areas", "regions"]:
            return self._show_areas(api_client, args)

        logger.error(f"Неизвестный тип справочника: {args.reference_type}")
        return 1

    def _show_industries(self, api_client, args) -> int:
        """Выводит справочник отраслей."""
        try:
            logger.info("Получение справочника отраслей...")
            industries = api_client.get("/industries")
        except Exception as e:
            logger.error(f"Ошибка при получении справочника отраслей: {e}")
            return 1

        # Фильтрация по названию
        if args.search:
            search_lower = args.search.lower()
            industries = [
                ind for ind in industries if search_lower in ind.get("name", "").lower()
            ]
            logger.info(
                f"Найдено отраслей по фильтру '{args.search}': {len(industries)}"
            )

        # Пагинация
        total = len(industries)
        page = args.page
        per_page = args.per_page
        if per_page > 0:
            start = page * per_page
            end = start + per_page
            industries = industries[start:end]
            logger.info(f"Страница {page + 1}, показано {len(industries)} из {total}")

        if args.format == "json":
            print(json.dumps(industries, ensure_ascii=False, indent=2))
        elif args.format == "simple":
            for ind in industries:
                print(f"{ind['id']}: {ind['name']}")
        else:  # table
            self._print_table(
                ["ID", "Название"],
                [(ind["id"], ind["name"]) for ind in industries],
                total=total,
                page=page,
                per_page=per_page,
            )

        return 0

    def _show_areas(self, api_client, args) -> int:
        """Выводит справочник регионов."""
        try:
            logger.info("Получение справочника регионов...")
            areas = api_client.get("/areas")
        except Exception as e:
            logger.error(f"Ошибка при получении справочника регионов: {e}")
            return 1

        # Фильтрация по стране
        if args.country:
            country_lower = args.country.lower()
            areas = [
                a
                for a in areas
                if country_lower in a.get("name", "").lower()
                or a.get("id") == args.country
            ]

        if args.format == "json":
            print(json.dumps(areas, ensure_ascii=False, indent=2))
        elif args.format == "tree":
            self._print_areas_tree(areas, max_depth=args.max_depth)
        elif args.format == "simple":
            flat_areas = self._flatten_areas(areas)
            # Фильтрация по названию
            if args.search:
                search_lower = args.search.lower()
                flat_areas = [
                    a for a in flat_areas if search_lower in a.get("name", "").lower()
                ]
                logger.info(
                    f"Найдено регионов по фильтру '{args.search}': {len(flat_areas)}"
                )
            # Пагинация
            total = len(flat_areas)
            page = args.page
            per_page = args.per_page
            if per_page > 0:
                start = page * per_page
                end = start + per_page
                flat_areas = flat_areas[start:end]
                logger.info(
                    f"Страница {page + 1}, показано {len(flat_areas)} из {total}"
                )
            for area in flat_areas:
                print(f"{area['id']}: {area['name']}")
        else:  # table
            flat_areas = self._flatten_areas(areas)
            # Фильтрация по названию
            if args.search:
                search_lower = args.search.lower()
                flat_areas = [
                    a for a in flat_areas if search_lower in a.get("name", "").lower()
                ]
                logger.info(
                    f"Найдено регионов по фильтру '{args.search}': {len(flat_areas)}"
                )
            # Пагинация
            total = len(flat_areas)
            page = args.page
            per_page = args.per_page
            if per_page > 0:
                start = page * per_page
                end = start + per_page
                flat_areas = flat_areas[start:end]
                logger.info(
                    f"Страница {page + 1}, показано {len(flat_areas)} из {total}"
                )
            self._print_table(
                ["ID", "Название", "Родитель"],
                [(a["id"], a["name"], a.get("parent_id", "-")) for a in flat_areas],
                total=total,
                page=page,
                per_page=per_page,
            )

        return 0

    def _flatten_areas(self, areas: list, parent_id: str | None = None) -> list:
        """Преобразует дерево регионов в плоский список."""
        result = []
        for area in areas:
            area_copy = dict(area)
            area_copy["parent_id"] = parent_id
            result.append(area_copy)
            if "areas" in area and area["areas"]:
                result.extend(self._flatten_areas(area["areas"], area["id"]))
        return result

    def _print_areas_tree(self, areas: list, indent: int = 0, max_depth: int = 3):
        """Выводит дерево регионов."""
        if indent >= max_depth:
            return
        for area in areas:
            print("  " * indent + f"{area['id']}: {area['name']}")
            if "areas" in area and area["areas"]:
                self._print_areas_tree(area["areas"], indent + 1, max_depth)

    def _print_table(
        self,
        headers: list,
        rows: list,
        total: int = 0,
        page: int = 0,
        per_page: int = 50,
    ):
        """Выводит данные в виде таблицы с информацией о пагинации."""
        if not rows:
            print("Нет данных для отображения")
            return

        # Вычисляем ширину колонок
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))

        # Выводим заголовок
        header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        separator = "-+-".join("-" * w for w in col_widths)
        print(header_line)
        print(separator)

        # Выводим строки
        for row in rows:
            print(
                " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
            )
