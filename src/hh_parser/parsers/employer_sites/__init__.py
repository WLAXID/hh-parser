"""
Парсинг сайтов работодателей.

Содержит компоненты для извлечения контактов
с официальных сайтов работодателей.
"""

from hh_parser.cli.config import (
    DEFAULT_SITE_CONFIG,
    SiteParserConfig,
)

from .site_parser import SiteContactParser

__all__ = (
    "SiteContactParser",
    "SiteParserConfig",
    "DEFAULT_SITE_CONFIG",
)
