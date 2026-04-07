"""Главный модуль CLI на Typer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
import urllib3
from rich.console import Console

# Отключаем предупреждения urllib3 о небезопасных соединениях
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = typer.Typer(
    name="hh-parser",
    help="Парсер для сбора данных о работодателях и контактах с сайта hh.ru",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()

# Логгер
logger = logging.getLogger(__package__)


@app.callback()
def global_options(
    ctx: typer.Context,
    verbosity: int = typer.Option(
        0,
        "-v",
        "--verbosity",
        count=True,
        help="Увеличить детальность вывода (можно использовать несколько раз: -v, -vv, -vvv)",
    ),
    config_dir: Optional[Path] = typer.Option(
        None,
        "-c",
        "--config-dir",
        "--config",
        help="Путь до директории с конфигом",
        exists=False,
    ),
    profile_id: Optional[str] = typer.Option(
        None,
        "--profile-id",
        "--profile",
        help="Используемый профиль — подкаталог в --config-dir",
    ),
    api_delay: Optional[float] = typer.Option(
        None,
        "-d",
        "--api-delay",
        "--delay",
        help="Задержка между запросами к API HH (секунды)",
    ),
    user_agent: Optional[str] = typer.Option(
        None,
        "--user-agent",
        help="User-Agent для запросов",
    ),
):
    """Глобальные опции для всех команд."""
    ctx.ensure_object(dict)
    ctx.obj["verbosity"] = verbosity
    ctx.obj["config_dir"] = config_dir
    ctx.obj["profile_id"] = profile_id
    ctx.obj["api_delay"] = api_delay
    ctx.obj["user_agent"] = user_agent


# Регистрация команд напрямую как функций
from .commands.authorize import authorize, logout
from .commands.export import contacts as export_contacts
from .commands.export import employers
from .commands.migrate_db import migrate_db, reset
from .commands.migrate_db import status as db_status
from .commands.parse import parse, stats
from .commands.parse_contacts import parse_contacts, show_contacts
from .commands.reference import areas, industries
from .commands.whoami import token, whoami

# Основные команды
app.command("parse")(parse)
app.command("stats")(stats)

app.command("parse-contacts")(parse_contacts)
app.command("show-contacts")(show_contacts)

app.command("export")(employers)
app.command("export-contacts")(export_contacts)

app.command("areas")(areas)
app.command("industries")(industries)

app.command("whoami")(whoami)
app.command("token")(token)

app.command("authorize")(authorize)
app.command("logout")(logout)

app.command("migrate-db")(migrate_db)
app.command("db-status")(db_status)
app.command("db-reset")(reset)


def main() -> None:
    """Точка входа для CLI."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Операция прервана пользователем[/yellow]")
        raise typer.Exit(code=130)
    except Exception as e:
        console.print(f"[bold red]Критическая ошибка:[/bold red] {e}")
        logger.exception("Необработанная ошибка")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    main()
