"""Команда whoami — информация о текущем пользователе."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..utils import get_tool, print_error, print_success

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
console = Console()


def whoami(ctx: typer.Context) -> None:
    """Показать информацию о текущем авторизованном пользователе."""
    tool = get_tool(ctx.obj)
    api_client = tool.api_client

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Информация о пользователе[/bold blue]",
        )
    )

    try:
        user = api_client.get("/me")

        # Создаём таблицу с информацией
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Параметр", style="cyan", width=20)
        table.add_column("Значение", style="white")

        # Основная информация
        full_name = " ".join(
            filter(
                None,
                [
                    user.get("first_name", ""),
                    user.get("last_name", ""),
                ],
            )
        )

        table.add_row("ID:", str(user.get("id", "—")))
        table.add_row("Имя:", full_name or "—")

        if user.get("middle_name"):
            table.add_row("Отчество:", user.get("middle_name"))

        table.add_row("Email:", user.get("email", "—") or "—")
        table.add_row("Телефон:", user.get("phone", "—") or "—")

        # Роли
        roles = []
        if user.get("is_applicant"):
            roles.append("[green]Соискатель[/green]")
        if user.get("is_employer"):
            roles.append("[blue]Работодатель[/blue]")
        if user.get("is_admin"):
            roles.append("[red]Администратор[/red]")

        table.add_row("Роли:", " | ".join(roles) if roles else "[dim]Нет[/dim]")

        console.print()
        console.print(table)

        # Дополнительная информация для работодателя
        if user.get("is_employer"):
            employer_info = user.get("employer", {})
            if employer_info:
                console.print()
                employer_table = Table(
                    title="Информация о работодателе", show_header=False
                )
                employer_table.add_column("Параметр", style="cyan")
                employer_table.add_column("Значение", style="white")

                employer_table.add_row("ID:", str(employer_info.get("id", "—")))
                employer_table.add_row("Название:", employer_info.get("name", "—"))

                console.print(employer_table)

        print_success("Авторизация активна")

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print_error(f"Не удалось получить информацию о пользователе: {e}")
        console.print("\n[yellow]Возможно, требуется авторизация:[/yellow]")
        console.print("[dim] hh-parser authorize[/dim]")
        raise typer.Exit(code=1)


def token(ctx: typer.Context) -> None:
    """Показать информацию о токене авторизации."""
    tool = get_tool(ctx.obj)

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Информация о токене[/bold blue]",
        )
    )

    config = tool.config
    token_info = config.get("token", {})

    if not token_info:
        console.print("[yellow]Токен не найден в конфигурации[/yellow]")
        console.print("\n[dim]Для авторизации выполните: hh-parser authorize[/dim]")
        raise typer.Exit(code=0)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Параметр", style="cyan", width=25)
    table.add_column("Значение", style="white")

    # Access token (частично скрытый)
    access_token = token_info.get("access_token", "")
    if access_token:
        # Показываем только первые и последние символы
        hidden_token = (
            f"{access_token[:8]}...{access_token[-8:]}"
            if len(access_token) > 20
            else "***"
        )
        table.add_row("Access Token:", hidden_token)
    else:
        table.add_row("Access Token:", "[red]Не установлен[/red]")

    # Refresh token (частично скрытый)
    refresh_token = token_info.get("refresh_token", "")
    if refresh_token:
        hidden_refresh = (
            f"{refresh_token[:8]}...{refresh_token[-8:]}"
            if len(refresh_token) > 20
            else "***"
        )
        table.add_row("Refresh Token:", hidden_refresh)
    else:
        table.add_row("Refresh Token:", "[dim]Нет[/dim]")

    # Срок действия
    expires_at = token_info.get("access_expires_at")
    if expires_at:
        from datetime import datetime

        try:
            # expires_at может быть int (timestamp) или строкой (ISO формат)
            if isinstance(expires_at, int):
                exp_dt = datetime.fromtimestamp(expires_at)
            else:
                exp_dt = datetime.fromisoformat(str(expires_at))
            is_expired = datetime.now() > exp_dt
            status = "[red]Истёк[/red]" if is_expired else "[green]Активен[/green]"
            table.add_row("Срок действия:", f"{exp_dt.isoformat()} {status}")
        except Exception:
            table.add_row("Срок действия:", str(expires_at))
    else:
        table.add_row("Срок действия:", "[dim]Неизвестно[/dim]")

    console.print()
    console.print(table)

    # Проверяем валидность токена
    try:
        api_client = tool.api_client
        user = api_client.get("/me")  # noqa: F841
        console.print()
        print_success("Токен валиден")
    except Exception:
        console.print()
        console.print("[yellow]Токен может быть недействительным[/yellow]")
        console.print("[dim]  Попробуйте переавторизоваться: hh-parser authorize[/dim]")
