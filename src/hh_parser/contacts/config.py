"""Конфигурация парсера сайта работодателя."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SiteParserConfig:
    """Конфигурация парсера сайта."""

    timeout: float = 30.0
    connect_timeout: float = 10.0
    delay_between_requests: float = 2.0
    max_redirects: int = 5
    max_pages_per_site: int = 10
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


DEFAULT_CONFIG = SiteParserConfig()


__all__ = ("SiteParserConfig", "DEFAULT_CONFIG")
