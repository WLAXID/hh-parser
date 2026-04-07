"""Команда экспорта данных."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

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
    storage = tool.storage

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

    # Получаем работодателей из БД
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Загрузка данных из БД...", total=None)
        employers_list = list(storage.employers.find())

    console.print(
        f"[dim]Загружено {format_number(len(employers_list))} работодателей[/dim]"
    )

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

    # Экспорт
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Экспорт...", total=len(employers_list))

            if format == "csv":
                import csv

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
                    for emp in employers_list:
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
                        progress.update(task, advance=1)

            else:  # json
                import json

                data = []
                for emp in employers_list:
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
                            "created_at": str(emp.created_at)
                            if emp.created_at
                            else None,
                            "updated_at": str(emp.updated_at)
                            if emp.updated_at
                            else None,
                        }
                    )
                    progress.update(task, advance=1)

                with open(output, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

        console.print()
        print_success(f"Экспорт завершён: {output}")
        console.print(
            f"[dim]   Экспортировано: {format_number(len(employers_list))} работодателей[/dim]"
        )
        console.print(
            f"[dim]   Размер файла: {output.stat().st_size / 1024:.1f} KB[/dim]"
        )

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
    storage = tool.storage

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

    # Получаем контакты
    contacts_list = list(storage.contacts.find())

    if employer_id:
        contacts_list = [c for c in contacts_list if c.employer_id == employer_id]

    if not contacts_list:
        print_info("Нет контактов для экспорта")
        raise typer.Exit(code=0)

    console.print(f"[dim]Найдено {format_number(len(contacts_list))} контактов[/dim]")

    # Экспорт
    try:
        if format == "csv":
            import csv

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

                for contact in contacts_list:
                    employer = storage.employers.get(contact.employer_id)
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

        else:  # json
            import json

            data = []
            for contact in contacts_list:
                employer = storage.employers.get(contact.employer_id)
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

        console.print()
        print_success(f"Экспорт завершён: {output}")
        console.print(
            f"[dim] Экспортировано: {format_number(len(contacts_list))} контактов[/dim]"
        )

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print_error(f"Ошибка экспорта: {e}")
        logger.exception("Ошибка экспорта контактов")
        raise typer.Exit(code=1)
