"""Команда миграции базы данных."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import questionary
import typer
from rich.console import Console
from rich.panel import Panel

from ..utils import get_tool, print_error, print_success

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
console = Console()


def migrate_db(ctx: typer.Context) -> None:
    """Миграция схемы базы данных."""
    tool = get_tool(ctx.obj)

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Миграция базы данных[/bold blue]",
        )
    )
    console.print(f"[dim]База данных: {tool.db_path}[/dim]")

    try:
        # Импортируем оригинальную операцию
        from hh_parser.operations.migrate_db import Operation

        operation = Operation()

        # Создаём args-подобный объект с нужными атрибутами
        class Args:
            list = False
            status = False
            apply = "auto"  # автоматическая миграция

        args = Args()

        # Выполняем миграцию
        result = operation.run(tool, args)

        if result == 0:
            console.print()
            print_success("Миграция завершена успешно!")
        else:
            print_error("Миграция завершилась с ошибкой")
            raise typer.Exit(code=1)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print_error(f"Ошибка миграции: {e}")
        logger.exception("Ошибка миграции")
        raise typer.Exit(code=1)


def status(ctx: typer.Context) -> None:
    """Показать статус базы данных."""
    tool = get_tool(ctx.obj)

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Статус базы данных[/bold blue]",
        )
    )

    if not tool.db_path.exists():
        console.print("[yellow]База данных не существует[/yellow]")
        console.print(f"[dim]Путь: {tool.db_path}[/dim]")
        console.print("\n[dim]Для создания выполните: hh-parser migrate-db[/dim]")
        return

    console.print(f"[dim]Путь: {tool.db_path}[/dim]")
    console.print(f"[dim]Размер: {tool.db_path.stat().st_size / 1024:.1f} KB[/dim]")

    try:
        storage = tool.storage

        # Подсчитываем записи
        employers = list(storage.employers.find())
        contacts = list(storage.contacts.find())

        console.print()
        console.print(f"[green]Работодателей:[/green] {len(employers)}")
        console.print(f"[green]Контактов:[/green] {len(contacts)}")

    except KeyboardInterrupt:
        raise
    except Exception as e:
        console.print(f"[red]Ошибка чтения: {e}[/red]")


def reset(
    ctx: typer.Context,
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Не спрашивать подтверждение",
    ),
) -> None:
    """Удалить и пересоздать базу данных."""
    tool = get_tool(ctx.obj)

    console.print()
    console.print(
        Panel.fit(
            "[bold red]Сброс базы данных[/bold red]",
        )
    )

    if not force:
        confirm = questionary.confirm(
            "Вы уверены, что хотите удалить все данные? Это действие необратимо!",
            default=False,
        ).ask()

        if not confirm:
            console.print("[yellow]Отменено[/yellow]")
            return

    try:
        # Удаляем файл БД
        if tool.db_path.exists():
            tool.db_path.unlink()
            console.print("[dim]Файл базы данных удалён[/dim]")

        # Выполняем миграцию для создания новой БД
        from hh_parser.operations.migrate_db import Operation

        operation = Operation()

        class Args:
            pass

        args = Args()
        operation.run(tool, args)

        print_success("База данных пересоздана")

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print_error(f"Ошибка: {e}")
        raise typer.Exit(code=1)
