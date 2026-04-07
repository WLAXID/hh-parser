"""Команда парсинга контактов."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, List, Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from ..config import ParseContactsConfig
from ..utils import format_number, get_tool, print_error, print_success

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
console = Console()


def parse_contacts(
    ctx: typer.Context,
    source: str = typer.Option(
        None,
        "--source",
        "-s",
        help="Источник контактов: api (только HH.RU API), site (только сайт), both (оба)",
    ),
    employer_id: Optional[List[int]] = typer.Option(
        None,
        "--employer-id",
        "-e",
        help="ID конкретных работодателей для парсинга",
    ),
    limit: int = typer.Option(
        0,
        "--limit",
        "-l",
        help="Ограничение количества работодателей (0 = без ограничений)",
    ),
    site_timeout: int = typer.Option(
        None,
        "--site-timeout",
        help="Таймаут для запросов к сайтам работодателей (секунды)",
    ),
    max_pages: int = typer.Option(
        None,
        "--max-pages",
        help="Максимум страниц для парсинга на одном сайте",
    ),
    delay: float = typer.Option(
        None,
        "--delay",
        "-d",
        help="Задержка между запросами к одному сайту (секунды)",
    ),
) -> None:
    """Парсинг контактов работодателей (email, телефоны)."""
    tool = get_tool(ctx.obj)

    # Загружаем конфигурацию из файла
    config_data = tool.config.get("parse_contacts", {})
    file_config = ParseContactsConfig.from_dict(config_data)

    # Определяем итоговые значения: приоритет у аргументов CLI, затем конфиг из файла
    final_source = source if source is not None else file_config.source

    # Валидация source
    if final_source not in ("api", "site", "both"):
        print_error(
            f"Неверный источник '{final_source}'. Допустимые значения: api, site, both"
        )
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]Парсинг контактов работодателей[/bold blue]",
            subtitle=f"[dim]Источник: {final_source}[/dim]",
        )
    )

    # Показать параметры
    params_table = Table(show_header=False, box=None, padding=(0, 2))
    params_table.add_column("Параметр", style="cyan")
    params_table.add_column("Значение", style="white")
    if employer_id:
        params_table.add_row(
            "ID работодателей:", ", ".join(str(e) for e in employer_id)
        )
    if limit > 0:
        params_table.add_row("Лимит:", str(limit))
    params_table.add_row("Таймаут сайта:", f"{file_config.timeout} сек")
    params_table.add_row("Макс. страниц:", str(file_config.max_pages_per_site))
    params_table.add_row("Задержка:", f"{file_config.delay_between_requests} сек")
    console.print(params_table)
    console.print()

    try:
        # Импортируем необходимые модули
        from hh_parser.parsers.deduplication import deduplicate_contacts
        from hh_parser.parsers.employer_sites.site_parser import SiteContactParser
        from hh_parser.parsers.hh_api.api_extractor import ApiContactExtractor

        # Получаем список работодателей
        if employer_id:
            employers_list = []
            for emp_id in employer_id:
                emp = tool.storage.employers.find_one(id=emp_id)
                if emp:
                    employers_list.append(emp)
                else:
                    console.print(
                        f"[yellow]Работодатель {emp_id} не найден в БД[/yellow]"
                    )
        else:
            employers_list = []
            for emp in tool.storage.employers.find():
                if emp.contacts_status and emp.contacts_status != "not_checked":
                    continue
                if not emp.site_url:
                    continue
                employers_list.append(emp)

        # Применяем лимит
        if limit > 0:
            employers_list = employers_list[:limit]

        if not employers_list:
            console.print("[yellow]Нет работодателей для обработки[/yellow]")
            return

        console.print()

        # Инициализируем экстракторы
        api_extractor = None
        site_parser = None

        # Переменная для хранения текущего URL (обновляется через callback)
        current_url_holder = {"url": ""}
        live_holder: dict = {}

        def on_url_change(url: str) -> None:
            """Callback для обновления текущего URL в прогресс-баре."""
            current_url_holder["url"] = url
            # Обновляем прогресс-бар в реальном времени
            if progress_holder and "task_id" in progress_holder:
                progress.update(
                    progress_holder["task_id"],
                    current_url=url,
                    refresh=False,
                )
            # Обновляем Live отображение если оно доступно
            if live_holder and "live" in live_holder:
                live_holder["live"].update(build_layout())

        if final_source in ("api", "both"):
            api_extractor = ApiContactExtractor(tool.api_client)

        if final_source in ("site", "both"):
            site_parser = SiteContactParser(file_config, on_url_change=on_url_change)

        # Статистика
        stats = {
            "employers_processed": 0,
            "contacts_found": 0,
            "emails_found": 0,
            "phones_found": 0,
            "errors": 0,
            "with_contacts": 0,
            "without_contacts": 0,
        }

        # Счётчики для прогресса и таблицы последних работодателей
        progress_holder = {
            "count": 0,
            "last_employers": [],  # Последние 5 работодателей
        }

        # Создаём прогресс-бар
        progress = Progress(
            TimeElapsedColumn(),
            "•",
            TextColumn(
                "[green]{task.fields[with_contacts]}[/green]/[red]{task.fields[without_contacts]}[/red]/[white]{task.fields[total_employers]}[/white]"
            ),
            "•",
            BarColumn(bar_width=40, complete_style="white", finished_style="green"),
            TextColumn("[white]{task.percentage:>6.2f}%[/white]"),
            "•",
            TextColumn("[dim]{task.fields[employer]}[/dim]"),
            "•",
            TextColumn("[dim]{task.fields[current_url]}[/dim]"),
            console=console,
        )

        def build_layout() -> Table:
            """Строит компоновку с таблицей последних работодателей и прогресс-баром."""
            layout_table = Table.grid(padding=1)
            layout_table.add_column(justify="left")

            # Таблица последних 5 работодателей
            if progress_holder["last_employers"]:
                last_table = Table(
                    title="Последние 5 работодателей",
                    show_header=True,
                    header_style="bold white",
                    expand=True,
                )
                last_table.add_column("ID", style="dim", justify="left", width=10)
                last_table.add_column(
                    "Название", style="white", justify="center", width=50
                )
                last_table.add_column("Регион", style="dim", justify="center", width=18)
                last_table.add_column("hh.ru", style="white", justify="left", width=40)
                last_table.add_column("Сайт", style="white", justify="left", width=40)
                last_table.add_column(
                    "Статус", style="white", justify="center", width=8
                )
                last_table.add_column("Почт", style="dim", justify="center", width=8)
                last_table.add_column("Номеров", style="dim", justify="center", width=8)

                for emp in progress_holder["last_employers"]:
                    status_str = emp.get("site_status", "-")
                    status_display = (
                        f"[green]{status_str}[/green]"
                        if status_str == "ok"
                        else f"[red]{status_str}[/red]"
                        if status_str == "fail"
                        else status_str
                    )
                    last_table.add_row(
                        str(emp["id"]),
                        emp["name"][:100] if emp["name"] else "-",
                        emp["region"][:18] if emp["region"] else "-",
                        emp["hh_url"][:40] if emp["hh_url"] else "-",
                        emp["site"][:40] if emp["site"] else "-",
                        status_display,
                        str(emp["emails"]),
                        str(emp["phones"]),
                    )
                layout_table.add_row(last_table)

            # Прогресс-бар
            layout_table.add_row(progress)

            return layout_table

        # Запускаем с Live для отображения таблицы и прогресс-бара
        try:
            with Live(build_layout(), console=console, refresh_per_second=4) as live:
                # Устанавливаем ссылку на live для callback
                live_holder["live"] = live

                task_id = progress.add_task(
                    "contacts",
                    total=len(employers_list),
                    with_contacts="0",
                    without_contacts="0",
                    total_employers=str(len(employers_list)),
                    employer="",
                    current_url="",
                )
                # Сохраняем task_id для обновления из callback
                progress_holder["task_id"] = task_id

                for i, employer in enumerate(employers_list):
                    try:
                        # Сбрасываем URL
                        current_url_holder["url"] = ""

                        # Извлекаем контакты
                        contacts = []
                        site_status = "-"  # Статус подключения к сайту

                        # API контакты
                        if api_extractor:
                            try:
                                for contact in api_extractor.extract_from_employer(
                                    employer.id, employer.name
                                ):
                                    contacts.append(contact)
                            except KeyboardInterrupt:
                                raise
                            except Exception as e:
                                logger.debug(f"API ошибка для {employer.id}: {e}")

                        # Контакты с сайта
                        if site_parser and employer.site_url:
                            current_url_holder["url"] = employer.site_url
                            live.update(build_layout())
                            try:
                                site_contacts = site_parser.parse_site(
                                    employer.id, employer.name, employer.site_url
                                )
                                contacts.extend(site_contacts)
                                site_status = "ok"  # Успешное подключение
                            except KeyboardInterrupt:
                                raise
                            except Exception:
                                site_status = "fail"  # Ошибка подключения

                        # Дедуплицируем и сохраняем
                        unique_contacts = deduplicate_contacts(contacts)
                        saved = tool.storage.contacts.save_many(unique_contacts)

                        # Обновляем статус работодателя
                        if len(unique_contacts) == 0:
                            employer.contacts_status = "no_contacts"
                        else:
                            employer.contacts_status = "has_contacts"
                        tool.storage.employers.save(employer)

                        # Обновляем статистику
                        stats["employers_processed"] += 1
                        stats["contacts_found"] += saved
                        emails_count = sum(
                            1 for c in unique_contacts if c.contact_type == "email"
                        )
                        phones_count = sum(
                            1 for c in unique_contacts if c.contact_type == "phone"
                        )
                        stats["emails_found"] += emails_count
                        stats["phones_found"] += phones_count

                        # Подсчёт with_contacts / without_contacts
                        if len(unique_contacts) > 0:
                            stats["with_contacts"] += 1
                        else:
                            stats["without_contacts"] += 1

                        # Добавляем работодателя в список последних
                        employer_info = {
                            "id": employer.id,
                            "name": employer.name or f"ID: {employer.id}",
                            "region": employer.area_name or "-",
                            "hh_url": employer.alternate_url or "-",
                            "site": employer.site_url or "-",
                            "site_status": site_status,
                            "emails": emails_count,
                            "phones": phones_count,
                        }
                        progress_holder["last_employers"].append(employer_info)
                        # Оставляем только последние 5
                        progress_holder["last_employers"] = progress_holder[
                            "last_employers"
                        ][-5:]

                        # Обновляем прогресс-бар
                        employer_display = (
                            employer.name[:50]
                            if employer.name
                            else f"ID: {employer.id}"
                        )
                        progress.update(
                            task_id,
                            completed=i + 1,
                            with_contacts=str(stats["with_contacts"]),
                            without_contacts=str(stats["without_contacts"]),
                            employer=employer_display,
                            current_url=current_url_holder["url"],
                            refresh=False,  # Live сам обновит
                        )
                        live.update(build_layout())

                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        stats["errors"] += 1
                        logger.exception(f"Ошибка обработки {employer.id}")
                        console.print(f"[dim red] Ошибка: {e}[/dim red]")

                # Финальное обновление
                progress.update(
                    task_id,
                    completed=len(employers_list),
                    with_contacts=str(stats["with_contacts"]),
                    without_contacts=str(stats["without_contacts"]),
                    employer="",
                    current_url="",
                )
                current_url_holder["url"] = ""
                live.update(build_layout())

        except KeyboardInterrupt:
            console.print("\n[yellow]Парсинг прерван пользователем[/yellow]")
            sys.exit(130)

        console.print()
        print_success("Парсинг контактов завершён!")

        # Показать итоговую статистику
        stats_panel = Panel(
            f"[bold]Обработано работодателей:[/bold] {format_number(stats['employers_processed'])}\n"
            f"[bold green]Email найдено:[/bold green] {format_number(stats['emails_found'])}\n"
            f"[bold yellow]Телефонов найдено:[/bold yellow] {format_number(stats['phones_found'])}\n"
            f"[bold blue]Всего контактов:[/bold blue] {format_number(stats['contacts_found'])}",
            title="[bold]Результаты парсинга[/bold]",
            border_style="green",
        )
        console.print(stats_panel)

        if stats["errors"] > 0:
            console.print(f"[yellow]Ошибок при обработке: {stats['errors']}[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Парсинг прерван пользователем[/yellow]")
        sys.exit(130)
    except Exception as e:
        print_error(f"Ошибка парсинга: {e}")
        logger.exception("Ошибка парсинга контактов")
        raise typer.Exit(code=1)


def show_contacts(
    ctx: typer.Context,
    employer_id: Optional[int] = typer.Option(
        None,
        "--employer-id",
        "-e",
        help="Фильтр по ID работодателя",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Сколько контактов показать",
    ),
) -> None:
    """Показать контакты из базы данных."""
    tool = get_tool(ctx.obj)
    storage = tool.storage

    contacts = list(storage.contacts.find())
    if employer_id:
        contacts = [c for c in contacts if c.employer_id == employer_id]

    if not contacts:
        console.print("[yellow]Контакты не найдены[/yellow]")
        return

    # Ограничиваем количество
    contacts = contacts[:limit]

    # Создаём таблицу
    table = Table(title="Контакты")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Работодатель", style="cyan", width=25)
    table.add_column("Контакт", style="green", width=35)
    table.add_column("Нормализованный", style="yellow", width=30)

    for contact in contacts:
        employer = storage.employers.get(contact.employer_id)
        employer_name = employer.name[:100] if employer else str(contact.employer_id)
        table.add_row(
            str(contact.id),
            employer_name,
            contact.value or "—",
            contact.normalized_value or "—",
            contact.source or "—",
        )

    console.print()
    console.print(table)

    # Показать итоги
    total = len(list(storage.contacts.find()))
    console.print(
        f"\n[dim]Показано {len(contacts)} из {format_number(total)} контактов[/dim]"
    )
