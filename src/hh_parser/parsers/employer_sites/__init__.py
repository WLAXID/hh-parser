"""
Парсинг сайтов работодателей.

Содержит компоненты для извлечения контактов
с официальных сайтов работодателей.
"""

from hh_parser.cli.config import ParseContactsConfig

from .site_parser import SiteContactParser

__all__ = (
    "SiteContactParser",
    "ParseContactsConfig",
)
