"""Команда для работы со справочниками HH.RU."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..utils import get_tool, print_error

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
console = Console()


def areas(
    ctx: typer.Context,
    parent: Optional[int] = typer.Option(
        None,
        "--parent",
        "-p",
        help="ID родительского региона для показа подрегионов",
    ),
    search: Optional[str] = typer.Option(
        None,
        "--search",
        "-s",
        help="Поиск по названию региона",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Максимальное количество результатов",
    ),
) -> None:
    """Показать справочник регионов."""
    tool = get_tool(ctx.obj)
    api_client = tool.api_client

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Справочник регионов[/bold blue]",
        )
    )

    try:
        # Получаем дерево регионов
        areas_tree = api_client.get("/areas")

        # Если указан родитель, фильтруем
        if parent:
            areas_list = _find_children(areas_tree, parent)
            parent_name = _find_name(areas_tree, parent)
            console.print(f"[dim]Подрегионы: {parent_name or parent}[/dim]")
        else:
            # Собираем все регионы в плоский список
            areas_list = _flatten_areas(areas_tree)

        # Поиск по названию
        if search:
            search_lower = search.lower()
            areas_list = [
                a for a in areas_list if search_lower in a.get("name", "").lower()
            ]
            console.print(f"[dim]Поиск: '{search}' — найдено {len(areas_list)}[/dim]")

        if not areas_list:
            console.print("[yellow]Регионы не найдены[/yellow]")
            return

        # Ограничиваем вывод
        if len(areas_list) > limit:
            console.print(
                f"[yellow]Показано {limit} из {len(areas_list)} регионов[/yellow]"
            )
            areas_list = areas_list[:limit]

        # Создаём таблицу
        table = Table(title="Регионы")
        table.add_column("ID", style="cyan", width=10)
        table.add_column("Название", style="white", width=40)
        table.add_column("Родитель", style="dim", width=30)

        for area in areas_list:
            parent_name = area.get("parent", {}).get("name", "")
            table.add_row(
                str(area.get("id", "")),
                area.get("name", ""),
                parent_name or "—",
            )

        console.print()
        console.print(table)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print_error(f"Ошибка получения справочника: {e}")
        raise typer.Exit(code=1)


def industries(
    ctx: typer.Context,
    search: Optional[str] = typer.Option(
        None,
        "--search",
        "-s",
        help="Поиск по названию отрасли",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Максимальное количество результатов",
    ),
) -> None:
    """Показать справочник отраслей."""
    tool = get_tool(ctx.obj)
    api_client = tool.api_client

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Справочник отраслей[/bold blue]",
        )
    )

    try:
        # Получаем список отраслей
        industries_list = api_client.get("/industries")

        # Поиск по названию
        if search:
            search_lower = search.lower()
            industries_list = [
                i for i in industries_list if search_lower in i.get("name", "").lower()
            ]
            console.print(
                f"[dim]Поиск: '{search}' — найдено {len(industries_list)}[/dim]"
            )

        if not industries_list:
            console.print("[yellow]Отрасли не найдены[/yellow]")
            return

        # Ограничиваем вывод
        if len(industries_list) > limit:
            console.print(
                f"[yellow]Показано {limit} из {len(industries_list)} отраслей[/yellow]"
            )
            industries_list = industries_list[:limit]

        # Создаём таблицу
        table = Table(title="Отрасли")
        table.add_column("ID", style="cyan", width=10)
        table.add_column("Название", style="white", width=50)

        for industry in industries_list:
            table.add_row(
                str(industry.get("id", "")),
                industry.get("name", ""),
            )

        console.print()
        console.print(table)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print_error(f"Ошибка получения справочника: {e}")
        raise typer.Exit(code=1)


def _flatten_areas(areas: list, parent: dict = None) -> list:
    """Преобразовать дерево регионов в плоский список."""
    result = []
    for area in areas:
        area_copy = dict(area)
        if parent:
            area_copy["parent"] = {"id": parent.get("id"), "name": parent.get("name")}
        result.append(area_copy)

        # Рекурсивно добавляем подрегионы
        if area.get("areas"):
            result.extend(_flatten_areas(area["areas"], area))

    return result


def _find_children(areas: list, parent_id: int) -> list:
    """Найти всех потомков указанного региона."""
    for area in areas:
        if area.get("id") == parent_id:
            return area.get("areas", [])
        if area.get("areas"):
            result = _find_children(area["areas"], parent_id)
            if result:
                return result
    return []


def _find_name(areas: list, area_id: int) -> Optional[str]:
    """Найти название региона по ID."""
    for area in areas:
        if area.get("id") == area_id:
            return area.get("name")
        if area.get("areas"):
            result = _find_name(area["areas"], area_id)
            if result:
                return result
    return None
