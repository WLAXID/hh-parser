"""Команда экспорта данных."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hh_parser.operations.export import (
    ExportContactsOperation,
    ExportEmployersOperation,
)

from ..utils import format_number, get_tool, print_error, print_info, print_success

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
console = Console()


def employers(
    ctx: typer.Context,
    format: Optional[str] = typer.Option(
        None,
        "--format",
        "-f",
        help="Формат экспорта: csv или json",
    ),
    area: Optional[str] = typer.Option(
        None,
        "--area",
        "-a",
        help="Фильтр по региону (название или ID)",
    ),
    min_vacancies: int = typer.Option(
        0,
        "--min-vacancies",
        "-m",
        help="Минимальное количество открытых вакансий",
    ),
    preview: bool = typer.Option(
        False,
        "--preview",
        "-p",
        help="Показать предпросмотр перед экспортом",
    ),
) -> None:
    """Экспорт данных о работодателях в CSV или JSON."""
    tool = get_tool(ctx.obj)

    # Если формат не указан, спрашиваем интерактивно
    if not format:
        format = questionary.select(
            "Выберите формат экспорта:",
            choices=["csv", "json"],
            default="csv",
        ).ask()

    if not format:
        raise typer.Exit(code=1)

    # Валидация формата
    if format not in ("csv", "json"):
        print_error(f"Неверный формат '{format}'. Допустимые значения: csv, json")
        raise typer.Exit(code=1)

    # Интерактивный ввод имени файла
    filename = questionary.text(
        "Введите имя файла (без расширения):",
        default="employers",
    ).ask()

    if not filename:
        console.print("[yellow]Экспорт отменён[/yellow]")
        raise typer.Exit(code=0)

    # Добавляем расширение если не указано
    if not filename.endswith(f".{format}"):
        filename = f"{filename}.{format}"

    # Создаём папку output если не существует
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output = output_dir / filename

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Экспорт работодателей[/bold blue]",
            subtitle=f"[dim]Формат: {format.upper()}[/dim]",
        )
    )

    # Получаем работодателей из БД для предпросмотра
    storage = tool.storage
    employers_list = list(storage.employers.find())

    # Применяем фильтры
    if area:
        employers_list = [
            e
            for e in employers_list
            if e.area_name and area.lower() in e.area_name.lower()
        ]
        console.print(
            f"[dim]Фильтр по региону: {len(employers_list)} работодателей[/dim]"
        )

    if min_vacancies > 0:
        employers_list = [
            e for e in employers_list if e.open_vacancies >= min_vacancies
        ]
        console.print(
            f"[dim]Фильтр по вакансиям: {len(employers_list)} работодателей[/dim]"
        )

    if not employers_list:
        print_info("Нет данных для экспорта с указанными фильтрами")
        raise typer.Exit(code=0)

    # Предпросмотр
    if preview:
        console.print()
        preview_table = Table(
            title=f"Предпросмотр (первые 10 из {len(employers_list)})"
        )
        preview_table.add_column("ID", style="dim", width=10)
        preview_table.add_column("Название", style="cyan", width=35)
        preview_table.add_column("Регион", style="green", width=20)
        preview_table.add_column("Вакансии", style="yellow", justify="right")

        for emp in employers_list[:10]:
            preview_table.add_row(
                str(emp.id),
                emp.name[:35] if emp.name else "—",
                emp.area_name[:20] if emp.area_name else "—",
                str(emp.open_vacancies),
            )

        console.print(preview_table)
        console.print()

        confirm = questionary.confirm(
            f"Экспортировать {format_number(len(employers_list))} работодателей?",
            default=True,
        ).ask()

        if not confirm:
            console.print("[yellow]Экспорт отменён[/yellow]")
            raise typer.Exit(code=0)

    # Выполняем экспорт через операцию
    try:
        operation = ExportEmployersOperation(tool)
        result = operation.run(
            format=format,
            output=output,
            area=area,
            min_vacancies=min_vacancies,
        )

        console.print()
        print_success(f"Экспорт завершён: {output}")
        console.print(
            f"[dim] Экспортировано: {format_number(result['count'])} работодателей[/dim]"
        )
        console.print(f"[dim] Размер файла: {result['size'] / 1024:.1f} KB[/dim]")

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print_error(f"Ошибка экспорта: {e}")
        logger.exception("Ошибка экспорта")
        raise typer.Exit(code=1)


def contacts(
    ctx: typer.Context,
    format: Optional[str] = typer.Option(
        None,
        "--format",
        "-f",
        help="Формат экспорта: csv или json",
    ),
    employer_id: Optional[int] = typer.Option(
        None,
        "--employer-id",
        "-e",
        help="Фильтр по ID работодателя",
    ),
) -> None:
    """Экспорт контактов в CSV или JSON."""
    tool = get_tool(ctx.obj)

    # Если формат не указан, спрашиваем интерактивно
    if not format:
        format = questionary.select(
            "Выберите формат экспорта:",
            choices=["csv", "json"],
            default="csv",
        ).ask()

    if not format:
        raise typer.Exit(code=1)

    # Интерактивный ввод имени файла
    filename = questionary.text(
        "Введите имя файла (без расширения):",
        default="contacts",
    ).ask()

    if not filename:
        console.print("[yellow]Экспорт отменён[/yellow]")
        raise typer.Exit(code=0)

    # Добавляем расширение если не указано
    if not filename.endswith(f".{format}"):
        filename = f"{filename}.{format}"

    # Создаём папку output если не существует
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output = output_dir / filename

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Экспорт контактов[/bold blue]",
            subtitle=f"[dim]Формат: {format.upper()}[/dim]",
        )
    )

    # Получаем контакты для отображения количества
    storage = tool.storage
    contacts_list = list(storage.contacts.find())

    if employer_id:
        contacts_list = [c for c in contacts_list if c.employer_id == employer_id]

    if not contacts_list:
        print_info("Нет контактов для экспорта")
        raise typer.Exit(code=0)

    console.print(f"[dim]Найдено {format_number(len(contacts_list))} контактов[/dim]")

    # Выполняем экспорт через операцию
    try:
        operation = ExportContactsOperation(tool)
        result = operation.run(
            format=format,
            output=output,
            employer_id=employer_id,
        )

        console.print()
        print_success(f"Экспорт завершён: {output}")
        console.print(
            f"[dim] Экспортировано: {format_number(result['count'])} контактов[/dim]"
        )

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print_error(f"Ошибка экспорта: {e}")
        logger.exception("Ошибка экспорта контактов")
        raise typer.Exit(code=1)
