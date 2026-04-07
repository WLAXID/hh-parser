"""Общие утилиты для CLI.

Использует rich для красивого вывода в терминал и questionary для интерактивного ввода.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from hh_parser.main import HHParserTool

# Глобальная консоль для вывода
console = Console()


def get_tool(ctx: dict) -> "HHParserTool":
    """Получить или создать экземпляр HHParserTool из контекста."""
    from hh_parser.main import HHParserTool

    tool = ctx.get("tool")
    if tool is None:
        tool = HHParserTool()
        ctx["tool"] = tool

    # Применить глобальные опции
    if ctx.get("config_dir"):
        tool.config_dir = ctx["config_dir"]
    if ctx.get("profile_id"):
        tool.profile_id = ctx["profile_id"]
    if ctx.get("verbosity"):
        tool.verbosity = ctx["verbosity"]
    if ctx.get("api_delay"):
        tool.api_delay = ctx["api_delay"]
    if ctx.get("user_agent"):
        tool.user_agent = ctx["user_agent"]

    return tool


def print_error(message: str) -> None:
    """Вывести ошибку в красном цвете."""
    console.print(f"[bold red][X] Ошибка:[/bold red] {message}")


def print_success(message: str) -> None:
    """Вывести успешное сообщение в зелёном цвете."""
    console.print(f"[bold green][OK][/bold green] {message}")


def print_info(message: str) -> None:
    """Вывести информационное сообщение в синем цвете."""
    console.print(f"[bold blue][i][/bold blue] {message}")


def print_warning(message: str) -> None:
    """Вывести предупреждение в жёлтом цвете."""
    console.print(f"[bold yellow][!][/bold yellow] {message}")


def format_number(n: int | float) -> str:
    """Форматировать число с разделителями тысяч."""
    return f"{n:,}".replace(",", " ")
