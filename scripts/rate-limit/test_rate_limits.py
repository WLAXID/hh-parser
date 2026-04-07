#!/usr/bin/env python3
"""
Скрипт для тестирования rate limits API HeadHunter.

Позволяет определить лимиты запросов для различных эндпоинтов HH API
и протестировать поведение при достижении лимитов.

Использование:
    python scripts/rate-limit/test_rate_limits.py [OPTIONS]

Примеры:
    python scripts/rate-limit/test_rate_limits.py test --requests 50
    python scripts/rate-limit/test_rate_limits.py find-min
    python scripts/rate-limit/test_rate_limits.py list
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Добавляем путь к проекту для импорта модулей
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Поддержка .env файла
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from hh_parser.api.client import HH_API_URL, BaseClient
from hh_parser.api.errors import (
    ApiError,
    CaptchaRequired,
    LimitExceeded,
)
from hh_parser.api.user_agent import generate_android_useragent

# Инициализация
app = typer.Typer(help="Тестирование rate limits HH API")
console = Console()


# Эндпоинты для тестирования
TEST_ENDPOINTS = {
    "vacancies": {
        "path": "vacancies",
        "params": {"text": "python", "per_page": 1},
        "description": "Поиск вакансий",
    },
    "vacancy_detail": {
        "path": "vacancies/{id}",
        "params": {},
        "description": "Детали вакансии (требуется ID)",
    },
    "employers": {
        "path": "employers/{id}",
        "params": {},
        "description": "Информация о работодателе",
    },
    "me": {
        "path": "me",
        "params": {},
        "description": "Информация о текущем пользователе (требуется токен)",
    },
    "dictionaries": {
        "path": "dictionaries",
        "params": {},
        "description": "Справочники",
    },
    "areas": {
        "path": "areas",
        "params": {},
        "description": "Регионы",
    },
    "industries": {
        "path": "industries",
        "params": {},
        "description": "Индустрии",
    },
    "metro": {
        "path": "metro",
        "params": {},
        "description": "Станции метро",
    },
}


@dataclass
class RequestResult:
    """Результат одного запроса."""

    success: bool
    status_code: int
    response_time: float
    timestamp: float
    error: str | None = None


@dataclass
class TestStats:
    """Статистика тестирования."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited: int = 0
    captcha_required: int = 0
    response_times: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def requests_per_second(self) -> float:
        if self.duration == 0:
            return 0.0
        return self.total_requests / self.duration

    @property
    def avg_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    @property
    def min_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return min(self.response_times)

    @property
    def max_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return max(self.response_times)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100


class RateLimitTester:
    """Тестер rate limits для HH API."""

    def __init__(
        self,
        access_token: str | None = None,
        user_agent: str | None = None,
        delay: float = 0.0,
    ):
        self.access_token = access_token
        self.user_agent = user_agent or generate_android_useragent()
        self.delay = delay
        self.stats = TestStats()

        self.client = BaseClient(
            base_url=HH_API_URL,
            user_agent=self.user_agent,
            delay=delay if delay > 0 else None,
        )

    def make_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> RequestResult:
        """Выполняет один запрос к API."""
        start_time = time.monotonic()
        timestamp = time.time()

        try:
            self.client.request("GET", endpoint, params=params)
            response_time = time.monotonic() - start_time
            return RequestResult(
                success=True,
                status_code=200,
                response_time=response_time,
                timestamp=timestamp,
            )

        except LimitExceeded as e:
            response_time = time.monotonic() - start_time
            return RequestResult(
                success=False,
                status_code=e.status_code,
                response_time=response_time,
                timestamp=timestamp,
                error="Rate limit exceeded",
            )

        except CaptchaRequired as e:
            response_time = time.monotonic() - start_time
            return RequestResult(
                success=False,
                status_code=e.status_code,
                response_time=response_time,
                timestamp=timestamp,
                error="Captcha required",
            )

        except ApiError as e:
            response_time = time.monotonic() - start_time
            return RequestResult(
                success=False,
                status_code=e.status_code,
                response_time=response_time,
                timestamp=timestamp,
                error=f"API error ({e.status_code})",
            )

        except Exception as e:
            response_time = time.monotonic() - start_time
            return RequestResult(
                success=False,
                status_code=0,
                response_time=response_time,
                timestamp=timestamp,
                error=f"Error: {str(e)[:50]}",
            )

    def run_test(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        num_requests: int = 100,
    ) -> TestStats:
        """Запускает тест rate limits с прогресс-баром."""
        self.stats = TestStats()
        self.stats.start_time = time.time()

        console.print()
        console.print(
            Panel.fit(
                "[bold]Тестирование rate limits[/bold]",
                subtitle=f"[dim]Эндпоинт: {endpoint} | Запросов: {num_requests}[/dim]",
            )
        )
        console.print()

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Выполнение запросов...", total=num_requests)

            for i in range(num_requests):
                result = self.make_request(endpoint, params)
                self._update_stats(result)

                status = "OK" if result.success else f"FAIL ({result.error})"
                progress.update(
                    task,
                    advance=1,
                    description=f"Запрос {i + 1}/{num_requests} - {status}",
                )

        self.stats.end_time = time.time()
        return self.stats

    def _update_stats(self, result: RequestResult) -> None:
        """Обновляет статистику."""
        self.stats.total_requests += 1
        self.stats.response_times.append(result.response_time)

        if result.success:
            self.stats.successful_requests += 1
        else:
            self.stats.failed_requests += 1
            if result.error:
                self.stats.errors.append(result.error)
                if "rate limit" in result.error.lower():
                    self.stats.rate_limited += 1
                elif "captcha" in result.error.lower():
                    self.stats.captcha_required += 1

    def print_report(self) -> None:
        """Выводит отчёт о тестировании."""
        console.print()

        # Таблица общей статистики
        stats_table = Table(title="Общая статистика", show_header=False, box=None)
        stats_table.add_column("Параметр")
        stats_table.add_column("Значение")

        stats_table.add_row("Всего запросов", f"{self.stats.total_requests}")
        stats_table.add_row("Успешных", f"{self.stats.successful_requests}")
        stats_table.add_row("Неуспешных", f"{self.stats.failed_requests}")

        if self.stats.rate_limited > 0:
            stats_table.add_row("Rate limited", f"{self.stats.rate_limited}")
        if self.stats.captcha_required > 0:
            stats_table.add_row("Captcha required", f"{self.stats.captcha_required}")

        stats_table.add_row("Процент успеха", f"{self.stats.success_rate:.1f}%")

        console.print(stats_table)
        console.print()

        # Таблица времени
        time_table = Table(title="Время ответа", show_header=True, box=None)
        time_table.add_column("Метрика")
        time_table.add_column("Значение")

        time_table.add_row("Среднее", f"{self.stats.avg_response_time * 1000:.1f} ms")
        time_table.add_row("Минимум", f"{self.stats.min_response_time * 1000:.1f} ms")
        time_table.add_row("Максимум", f"{self.stats.max_response_time * 1000:.1f} ms")
        time_table.add_row("Длительность теста", f"{self.stats.duration:.2f} s")
        time_table.add_row("Запросов/сек", f"{self.stats.requests_per_second:.2f}")

        console.print(time_table)

        if self.stats.errors:
            console.print()
            error_table = Table(title="Ошибки", show_header=True, box=None)
            error_table.add_column("Тип ошибки")
            error_table.add_column("Количество")

            error_counts: dict[str, int] = {}
            for error in self.stats.errors:
                error_type = error.split(":")[0] if ":" in error else error
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

            for error_type, count in sorted(error_counts.items(), key=lambda x: -x[1]):
                error_table.add_row(error_type, str(count))

            console.print(error_table)

        console.print()


def find_min_delay(
    endpoint: str,
    params: dict[str, Any] | None = None,
    start_delay: float = 2.0,
    min_delay: float = 0.01,
    requests_per_test: int = 10,
    success_threshold: float = 95.0,
    access_token: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """
    Находит минимальную безопасную задержку между запросами.

    Тестирует разные задержки от start_delay до min_delay и строит таблицу результатов.
    """
    console.print()
    console.print(
        Panel.fit(
            "[bold]Поиск минимальной безопасной задержки[/bold]",
            subtitle=f"[dim]Эндпоинт: {endpoint} | Диапазон: {start_delay}s → {min_delay}s[/dim]",
        )
    )
    console.print()

    # Генерируем список задержек для тестирования
    delays_to_test = []

    current = start_delay
    while current >= min_delay:
        delays_to_test.append(round(current, 3))
        current *= 0.7
        if current < min_delay:
            break

    if min_delay not in delays_to_test:
        delays_to_test.append(min_delay)

    delays_to_test = sorted(delays_to_test, reverse=True)

    results: list[dict[str, Any]] = []
    best_delay = start_delay
    best_success_rate = 0.0

    user_agent = user_agent or generate_android_useragent()

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        main_task = progress.add_task(
            "Тестирование задержек...",
            total=len(delays_to_test),
        )

        for delay in delays_to_test:
            progress.update(
                main_task,
                description=f"Тестируем задержку: {delay:.3f}s",
            )

            success_count = 0
            test_client = BaseClient(
                base_url=HH_API_URL,
                user_agent=user_agent,
                delay=delay if delay > 0 else None,
            )

            for _ in range(requests_per_test):
                try:
                    test_client.request("GET", endpoint, params=params)
                    success_count += 1
                except (LimitExceeded, CaptchaRequired, ApiError):
                    pass
                except Exception:
                    pass

            success_rate = (success_count / requests_per_test) * 100

            results.append(
                {
                    "delay": delay,
                    "success_rate": success_rate,
                    "success_count": success_count,
                    "total_requests": requests_per_test,
                }
            )

            if success_rate >= success_threshold and delay < best_delay:
                best_delay = delay
                best_success_rate = success_rate

            progress.advance(main_task)

    # Строим таблицу результатов
    console.print()
    
    results_table = Table(
    title="Результаты тестирования задержек",
    show_header=True,
    )
    results_table.add_column("Задержка", justify="right")
    results_table.add_column("Успешно", justify="center")
    results_table.add_column("Процент", justify="center")
    results_table.add_column("Статус", justify="center")

    for r in results:
        delay_str = f"{r['delay']:.3f}s"
        success_str = f"{r['success_count']}/{r['total_requests']}"

        rate = r["success_rate"]
        if rate >= success_threshold:
            rate_str = f"{rate:.0f}%"
            status = "OK"
        elif rate >= 80:
            rate_str = f"{rate:.0f}%"
            status = "WARN"
        else:
            rate_str = f"{rate:.0f}%"
            status = "FAIL"

        if r["delay"] == best_delay and r["success_rate"] >= success_threshold:
            delay_str = f"{delay_str} <--"

        results_table.add_row(delay_str, success_str, rate_str, status)

    console.print(results_table)
    console.print()

    # Итоговый результат
    safe_delays = [r for r in results if r["success_rate"] >= success_threshold]
    if safe_delays:
        recommended = min(safe_delays, key=lambda x: x["delay"])
        console.print(
            Panel.fit(
                f"Минимальная безопасная задержка: {recommended['delay']:.3f}s\n"
                f"Процент успеха: {recommended['success_rate']:.0f}%",
                title="Результат",
            )
        )
        best_delay = recommended["delay"]
        best_success_rate = recommended["success_rate"]
    else:
        console.print(
            Panel.fit(
                f"Не найдена безопасная задержка\n"
                f"Ни одна из протестированных задержек не достигла порога {success_threshold}%\n"
                f"Попробуйте увеличить начальную задержку (--start)",
                title="Результат",
            )
        )

    return {
        "min_delay": best_delay,
        "success_rate": best_success_rate,
        "results": results,
        "config": {
            "endpoint": endpoint,
            "start_delay": start_delay,
            "min_delay": min_delay,
            "requests_per_test": requests_per_test,
            "success_threshold": success_threshold,
        },
    }


def list_endpoints() -> None:
    """Выводит список доступных эндпоинтов."""
    console.print()

    table = Table(title="Доступные эндпоинты для тестирования")
    table.add_column("Название", no_wrap=True)
    table.add_column("Путь")
    table.add_column("Описание")
    table.add_column("Параметры")

    for name, info in TEST_ENDPOINTS.items():
        params_str = str(info["params"]) if info["params"] else "-"
        table.add_row(
            name,
            info["path"],
            info["description"],
            params_str[:30] + "..." if len(params_str) > 30 else params_str,
        )

    console.print(table)
    console.print()


@app.command("list")
def list_endpoints_cmd() -> None:
    """Показать список доступных эндпоинтов."""
    list_endpoints()


@app.command("test")
def test_rate_limits(
    requests: int = typer.Option(
        100,
        "--requests",
        "-n",
        help="Количество запросов",
    ),
    endpoint: str = typer.Option(
        "vacancies",
        "--endpoint",
        "-e",
        help="Эндпоинт для тестирования",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        "-t",
        help="Access token для авторизации",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Путь для сохранения отчёта в JSON",
    ),
) -> None:
    """Запустить тест rate limits."""
    access_token = token or os.environ.get("HH_ACCESS_TOKEN")

    if endpoint not in TEST_ENDPOINTS:
        console.print(f"[red]Ошибка: Неизвестный эндпоинт '{endpoint}'[/red]")
        console.print(f"Доступные эндпоинты: {', '.join(TEST_ENDPOINTS.keys())}")
        raise typer.Exit(1)

    endpoint_info = TEST_ENDPOINTS[endpoint]
    endpoint_path = endpoint_info["path"]
    endpoint_params = endpoint_info["params"].copy()

    if "{id}" in endpoint_path:
        if endpoint == "vacancy_detail":
            endpoint_path = endpoint_path.replace("{id}", "48968543")
        elif endpoint == "employers":
            endpoint_path = endpoint_path.replace("{id}", "1746308")

    tester = RateLimitTester(access_token=access_token)
    tester.run_test(
        endpoint=endpoint_path,
        params=endpoint_params if endpoint_params else None,
        num_requests=requests,
    )
    tester.print_report()

    if output:
        report = {
            "timestamp": datetime.now().isoformat(),
            "endpoint": endpoint_path,
            "stats": {
                "total_requests": tester.stats.total_requests,
                "successful_requests": tester.stats.successful_requests,
                "failed_requests": tester.stats.failed_requests,
                "success_rate": tester.stats.success_rate,
                "avg_response_time": tester.stats.avg_response_time,
            },
        }
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        console.print(f"Отчёт сохранён: {output_path}")


@app.command("find-min")
def find_min_delay_cmd(
    endpoint: str = typer.Option(
        "vacancies",
        "--endpoint",
        "-e",
        help="Эндпоинт для тестирования",
    ),
    start_delay: float = typer.Option(
        2.0,
        "--start",
        "-s",
        help="Начальная задержка (секунды)",
    ),
    min_delay: float = typer.Option(
        0.01,
        "--min",
        "-m",
        help="Минимальная задержка для тестирования (секунды)",
    ),
    requests_per_test: int = typer.Option(
        10,
        "--requests",
        "-n",
        help="Запросов на каждый тест задержки",
    ),
    threshold: float = typer.Option(
        95.0,
        "--threshold",
        "-t",
        help="Минимальный процент успеха",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        help="Access token для авторизации",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Путь для сохранения результатов в JSON",
    ),
) -> None:
    """Найти минимальную безопасную задержку между запросами."""
    access_token = token or os.environ.get("HH_ACCESS_TOKEN")

    if endpoint not in TEST_ENDPOINTS:
        console.print(f"[red]Ошибка: Неизвестный эндпоинт '{endpoint}'[/red]")
        console.print(f"Доступные эндпоинты: {', '.join(TEST_ENDPOINTS.keys())}")
        raise typer.Exit(1)

    endpoint_info = TEST_ENDPOINTS[endpoint]
    endpoint_path = endpoint_info["path"]
    endpoint_params = endpoint_info["params"].copy()

    if "{id}" in endpoint_path:
        if endpoint == "vacancy_detail":
            endpoint_path = endpoint_path.replace("{id}", "48968543")
        elif endpoint == "employers":
            endpoint_path = endpoint_path.replace("{id}", "1746308")

    result = find_min_delay(
        endpoint=endpoint_path,
        params=endpoint_params if endpoint_params else None,
        start_delay=start_delay,
        min_delay=min_delay,
        requests_per_test=requests_per_test,
        success_threshold=threshold,
        access_token=access_token,
    )

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        console.print(f"Результат сохранён: {output_path}")


@app.callback()
def main(
    ctx: typer.Context,
) -> None:
    """Тестирование rate limits HH API."""
    pass


if __name__ == "__main__":
    app()
