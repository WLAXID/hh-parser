"""Конфигурация CLI-команд парсера.

Содержит классы конфигурации для всех команд парсинга:
- ParseContactsConfig: конфигурация парсинга контактов
- ParseEmployersConfig: конфигурация парсинга работодателей
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParseContactsConfig:
    """Конфигурация команды парсинга контактов."""

    source: str = "both"
    # Параметры HTTP-клиента для парсинга сайтов
    timeout: float = 30.0
    connect_timeout: float = 10.0
    delay_between_requests: float = 2.0
    max_redirects: int = 5
    max_pages_per_site: int = 10
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ParseContactsConfig":
        """
        Создать конфигурацию из словаря.

        Args:
            data: Словарь с параметрами конфигурации

        Returns:
            Экземпляр ParseContactsConfig
        """
        if not data:
            return cls()

        return cls(
            source=data.get("source", "both"),
            timeout=data.get("timeout", 30.0),
            connect_timeout=data.get("connect_timeout", 10.0),
            delay_between_requests=data.get("delay_between_requests", 2.0),
            max_redirects=data.get("max_redirects", 5),
            max_pages_per_site=data.get("max_pages_per_site", 10),
            user_agent=data.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ),
        )


@dataclass
class ParseEmployersConfig:
    """Конфигурация команды парсинга работодателей."""

    per_page: int = 100
    sort_by: str = "by_name"
    mode: str = "full"
    # Параметры HTTP-клиента для API запросов
    timeout: float = 30.0
    connect_timeout: float = 10.0
    delay_between_requests: float = 0.345
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ParseEmployersConfig":
        """
        Создать конфигурацию из словаря.

        Args:
            data: Словарь с параметрами конфигурации

        Returns:
            Экземпляр ParseEmployersConfig
        """
        if not data:
            return cls()

        return cls(
            per_page=data.get("per_page", 100),
            sort_by=data.get("sort_by", "by_name"),
            mode=data.get("mode", "full"),
            timeout=data.get("timeout", 30.0),
            connect_timeout=data.get("connect_timeout", 10.0),
            delay_between_requests=data.get("delay_between_requests", 0.345),
            user_agent=data.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ),
        )


__all__ = (
    "ParseContactsConfig",
    "ParseEmployersConfig",
)
