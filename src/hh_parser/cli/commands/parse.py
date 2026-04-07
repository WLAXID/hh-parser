"""Команда парсинга работодателей."""

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

from ..config import ParseEmployersConfig
from ..utils import format_number, get_tool, print_error, print_info, print_success

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
console = Console()


def parse(
    ctx: typer.Context,
    area: Optional[List[str]] = typer.Option(
        None, "--area", "-a", help="Фильтр по региону (ID региона, можно указать несколько)",
    ),
    only_with_vacancies: bool = typer.Option(
        False, "--only-with-vacancies", help="Только работодатели с открытыми вакансиями",
    ),
    sort_by: str = typer.Option(
        None, "--sort-by", "-s", help="Сортировка результатов",
    ),
    per_page: int = typer.Option(
        None, "--per-page", help="Количество результатов на странице (максимум 100)",
    ),
    mode: str = typer.Option(
        None, "--mode", "-m", help="Режим работы: fast (базовая информация), full (с расчётом avg_responses), stats-only (обновить статистику)",
    ),
    resume: bool = typer.Option(
        False, "--resume", "-r", help="Возобновить парсинг, пропуская уже существующих работодателей",
    ),
    limit: int = typer.Option(
        0, "--limit", "-l", help="Ограничение количества работодателей (0 = без ограничений)",
    ),
) -> None:
    """Парсинг работодателей с hh.ru API."""
    tool = get_tool(ctx.obj)

    # Загружаем конфигурацию из файла
    config_data = tool.config.get("parse", {})
    file_config = ParseEmployersConfig.from_dict(config_data)

    # Определяем итоговые значения: приоритет у аргументов CLI, затем конфиг из файла
    final_sort_by = sort_by if sort_by is not None else file_config.sort_by
    final_per_page = per_page if per_page is not None else file_config.per_page
    final_mode = mode if mode is not None else file_config.mode

    # Валидация mode
    if final_mode not in ("fast", "full", "stats-only"):
        print_error(
            f"Неверный режим '{final_mode}'. Допустимые значения: fast, full, stats-only"
        )
        raise typer.Exit(code=1)

    # Валидация sort_by
    if final_sort_by not in ("by_name", "by_vacancies_open"):
        print_error(
            f"Неверная сортировка '{final_sort_by}'. Допустимые значения: by_name, by_vacancies_open"
        )
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel.fit(
            "[bold white]Парсинг работодателей[/bold white]",
            subtitle=f"[dim]Режим: {final_mode}[/dim]",
        )
    )

    # Показать параметры
    params_table = Table(show_header=False, box=None, padding=(0, 2))
    params_table.add_column("Параметр", style="cyan")
    params_table.add_column("Значение", style="white")
    if area:
        params_table.add_row("Регионы:", ", ".join(area))
    params_table.add_row("Только с вакансиями:", "Да" if only_with_vacancies else "Нет")
    params_table.add_row("Режим:", final_mode)
    params_table.add_row("Сортировка:", final_sort_by)
    params_table.add_row("На странице:", str(final_per_page))
    params_table.add_row("Продолжить:", "Да" if resume else "Нет")
    if area:
        console.print(params_table)
        console.print()

    try:
        # Импортируем оригинальную операцию
        from hh_parser.operations.parse import Operation

        operation = Operation()

        # Создаём args-подобный объект для совместимости
        class Args:
            def __init__(self):
                self.area = area
                self.only_with_vacancies = only_with_vacancies
                self.sort_by = final_sort_by
                self.per_page = final_per_page
                self.mode = final_mode
                self.resume = resume
                self.limit = limit

        args = Args()

        # Счётчики для прогресса
        progress_holder = {
            "count": 0,
            "with_site": 0,
            "without_site": 0,
            "total_found": 0,
            "last_employers": [],  # Последние 5 работодателей
        }

        # Создаём прогресс-бар
        progress = Progress(
            TimeElapsedColumn(),
            "•",
            TextColumn(
                "[green]{task.fields[with_site]}[/green]/[red]{task.fields[without_site]}[/red]/[white]{task.fields[total_employers]}[/white]"
            ),
            "•",
            BarColumn(bar_width=40, complete_style="white", finished_style="green"),
            TextColumn("[white]{task.percentage:>6.2f}%[/white]"),
            "•",
            TextColumn("[dim]{task.fields[employer]}[/dim]"),
            console=console,
        )

        task_id = progress.add_task(
            "parse",
            total=100,
            action="Инициализация...",
            employer="",
            current="0",
            total_employers="?",
            with_site="0",
            without_site="0",
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
                last_table.add_column(
                    "Вакансий", style="dim", justify="center", width=8
                )
                last_table.add_column("hh.ru", style="white", justify="left", width=40)
                last_table.add_column("Сайт", style="white", justify="left", width=40)

                for emp in progress_holder["last_employers"]:
                    last_table.add_row(
                        str(emp["id"]),
                        emp["name"][:35] if emp["name"] else "-",
                        emp["region"][:18] if emp["region"] else "-",
                        str(emp["vacancies"]),
                        emp["hh_url"][:40] if emp["hh_url"] else "-",
                        emp["site"][:40] if emp["site"] else "-",
                    )
                layout_table.add_row(last_table)

            # Прогресс-бар
            layout_table.add_row(progress)

            return layout_table

        # Создаём callback-функцию для обновления прогресса
        def progress_callback(
            employer_name: str,
            employer_id: int,
            region: str,
            has_site: bool = False,
            total_found: int = 0,
            site_url: str | None = None,
            open_vacancies: int = 0,
            alternate_url: str | None = None,
        ):
            """Обновляет отображение текущего работодателя."""
            progress_holder["count"] += 1
            if has_site:
                progress_holder["with_site"] += 1
            else:
                progress_holder["without_site"] += 1

            # Добавляем работодателя в список последних
            employer_info = {
                "id": employer_id,
                "name": employer_name or f"ID: {employer_id}",
                "region": region or "-",
                "vacancies": open_vacancies,
                "site": site_url or "-",
                "hh_url": alternate_url or "-",
            }
            progress_holder["last_employers"].append(employer_info)
            # Оставляем только последние 5
            progress_holder["last_employers"] = progress_holder["last_employers"][-5:]

            # Обновляем total_found если передано новое значение
            if total_found > 0:
                # API hh.ru ограничивает результаты до 5000
                progress_holder["total_found"] = min(total_found, 5000)

            employer_display = (
                employer_name[:50] if employer_name else f"ID: {employer_id}"
            )
            total_val = progress_holder["total_found"]

            # Для прогресс-бара используем максимум 5000 (ограничение API)
            progress_total = min(total_val, 5000) if total_val > 0 else 100
            progress.update(
                task_id,
                total=progress_total,
                completed=progress_holder["count"],
                action=f"[{progress_holder['count']}]",
                employer=employer_display,
                current=str(progress_holder["count"]),
                total_employers=str(total_val) if total_val > 0 else "?",
                with_site=str(progress_holder["with_site"]),
                without_site=str(progress_holder["without_site"]),
                refresh=False,  # Live сам обновит
            )

        # Запускаем с Live для отрисовки в одном месте
        with Live(build_layout(), console=console, refresh_per_second=4) as live:
            # Функция для обновления live
            def update_live():
                live.update(build_layout())

            # Переопределяем callback для обновления live
            original_callback = progress_callback

            def progress_callback_with_live(*args, **kwargs):
                original_callback(*args, **kwargs)
                update_live()

            # Выполняем парсинг с callback
            result = operation.run(
                tool, args, progress_callback=progress_callback_with_live
            )

            if result == 0:
                console.print()
                print_success("Парсинг завершён успешно!")

                # Показать статистику
                storage = tool.storage
                employers_count = storage.employers.count_total()
                stats_table = Table(title="Статистика базы данных", show_header=False)
                stats_table.add_column("Параметр", style="cyan")
                stats_table.add_column("Значение", style="green", justify="right")
                stats_table.add_row("Всего работодателей:", format_number(employers_count))
                console.print()
                console.print(stats_table)
            else:
                print_error("Парсинг завершился с ошибкой")
                raise typer.Exit(code=1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Парсинг прерван пользователем[/yellow]")
        sys.exit(130)
    except Exception as e:
        print_error(f"Ошибка парсинга: {e}")
        logger.exception("Ошибка парсинга")
        raise typer.Exit(code=1)


def stats(ctx: typer.Context) -> None:
    """Показать статистику базы данных работодателей."""
    tool = get_tool(ctx.obj)
    storage = tool.storage

    employers = list(storage.employers.find())
    if not employers:
        print_info("База данных пуста")
        return

    # Подсчёт статистики
    total = len(employers)
    with_vacancies = sum(1 for e in employers if e.open_vacancies > 0)
    total_vacancies = sum(e.open_vacancies for e in employers)
    avg_vacancies = total_vacancies / total if total > 0 else 0

    # Создаём таблицу
    table = Table(title="Статистика работодателей")
    table.add_column("Параметр", style="cyan")
    table.add_column("Значение", style="green", justify="right")

    table.add_row("Всего работодателей", format_number(total))
    table.add_row(
        "С открытыми вакансиями",
        f"{format_number(with_vacancies)} ({with_vacancies / total * 100:.1f}%)"
        if total > 0
        else "0.00%",
    )
    table.add_row("Всего вакансий", format_number(total_vacancies))
    table.add_row("Среднее вакансий", f"{avg_vacancies:.1f}")

    console.print()
    console.print(table)

    # Топ регионов
    regions: dict = {}
    for e in employers:
        if e.area_name:
            regions[e.area_name] = regions.get(e.area_name, 0) + 1

    if regions:
        top_regions = sorted(regions.items(), key=lambda x: x[1], reverse=True)[:5]
        regions_table = Table(title="Топ регионов по количеству работодателей")
        regions_table.add_column("Регион", style="cyan")
        regions_table.add_column("Количество", style="green", justify="right")

        for region, count in top_regions:
            regions_table.add_row(region, format_number(count))

        console.print()
        console.print(regions_table)
