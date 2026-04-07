"""Команда авторизации."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from ..utils import get_tool, print_error, print_success

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
console = Console()


@dataclass(slots=True)
class AuthorizeArgs:
    username: str | None
    password: str | None
    no_headless: bool
    manual: bool


def _prompt_username() -> str | None:
    value = questionary.text(
        "Введите email или телефон:",
        validate=lambda x: len(x.strip()) > 0 or "Введите значение",
    ).ask()

    if value is None:
        return None

    value = value.strip()
    return value or None


def _prompt_password() -> str | None:
    value = questionary.password("Введите пароль:").ask()
    if value is None:
        return None
    value = value.strip()
    return value or None


def _build_operation_args(
    username: str | None,
    password: str | None,
    no_headless: bool,
    manual: bool,
) -> AuthorizeArgs:
    return AuthorizeArgs(
        username=username,
        password=password,
        no_headless=no_headless,
        manual=manual,
    )


def authorize(
    ctx: typer.Context,
    username: str | None = typer.Argument(
        None,
        help="Email или телефон для входа",
    ),
    password: str | None = typer.Option(
        None,
        "-p",
        "--password",
        help="Пароль для входа",
    ),
    no_headless: bool = typer.Option(
        False,
        "-n",
        "--no-headless",
        help="Показать окно браузера (не использовать headless режим)",
    ),
    manual: bool = typer.Option(
        False,
        "-m",
        "--manual",
        help="Ручной режим - входить под руководством пользователя",
    ),
) -> None:
    """Авторизация через Playwright для получения токена"""
    tool = get_tool(ctx.obj)

    if not manual and not username:
        username = _prompt_username()
        if not username:
            print_error("Имя пользователя не может быть пустым")
            raise typer.Exit(code=1)

    if not manual and not password:
        password = _prompt_password()

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Авторизация[/bold blue]",
            subtitle="[dim]Playwright[/dim]",
        )
    )

    try:
        from hh_parser.operations.authorize import (
            BrowserClosedError,
            OAuthTimeoutError,
            Operation,
        )
    except ImportError as exc:
        print_error(f"Не удалось загрузить команду авторизации: {exc}")
        raise typer.Exit(code=1) from exc

    operation = Operation()
    args = _build_operation_args(
        username=username,
        password=password,
        no_headless=no_headless,
        manual=manual,
    )

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Ожидание авторизации...", total=None)  # noqa: F841
            operation.run(tool, args)

        tool.save_token()

        console.print()
        print_success("Авторизация прошла успешно!")
        console.print(f"[dim]Профиль: {tool.config_path}[/dim]")
        console.print("[dim]Токен сохранён[/dim]")

    except BrowserClosedError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    except OAuthTimeoutError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        msg = str(exc).strip()
        if "Playwright" in msg or "playwright" in msg:
            print_error(
                "Playwright не установлен или не доступен. "
                "Установите зависимости и выполните: playwright install chromium"
            )
        else:
            print_error(f"Ошибка авторизации: {msg}")
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt as exc:
        console.print("\n[yellow]Авторизация отменена пользователем[/yellow]")
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        logger.exception("Неожиданная ошибка авторизации")
        print_error(f"Ошибка авторизации: {exc}")
        raise typer.Exit(code=1) from exc


def _remove_token_from_config(config_file: Path) -> None:
    if not config_file.exists():
        return

    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Некорректный JSON в {config_file}") from exc

    if "token" in config:
        del config["token"]
        config_file.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def logout(ctx: typer.Context) -> None:
    """Удалить сохранённый токен и cookies."""
    tool = get_tool(ctx.obj)

    confirm = questionary.confirm(
        "Вы уверены, что хотите удалить токен и cookies?",
        default=False,
    ).ask()

    if not confirm:
        console.print("[yellow]Отменено[/yellow]")
        return

    try:
        config_file = tool.config_path / "config.json"
        _remove_token_from_config(config_file)

        cookies_file = tool.cookies_file
        if cookies_file.exists():
            cookies_file.unlink()

    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        print_error(f"Не удалось удалить данные авторизации: {exc}")
        raise typer.Exit(code=1) from exc

    print_success("Токен и cookies удалены")
