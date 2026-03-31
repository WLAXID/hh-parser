from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

QUERIES_PATH: Path = Path(__file__).parent / "queries"
MIGRATION_PATH: Path = QUERIES_PATH / "migrations"


logger: logging.Logger = logging.getLogger(__package__)


def init_db(conn: sqlite3.Connection) -> None:
    """Создает схему БД"""
    changes_before = conn.total_changes

    conn.executescript((QUERIES_PATH / "schema.sql").read_text(encoding="utf-8"))

    if conn.total_changes > changes_before:
        logger.info("Применена схема бд")
    # else:
    # logger.debug("База данных не изменилась.")

    # Применяем схему контактов
    schema_contacts_path = QUERIES_PATH / "schema_contacts.sql"
    if schema_contacts_path.exists():
        changes_before_contacts = conn.total_changes
        conn.executescript(schema_contacts_path.read_text(encoding="utf-8"))
        if conn.total_changes > changes_before_contacts:
            logger.info("Применена схема контактов")


def list_migrations() -> list[str]:
    """Выводит имена миграций без расширения, отсортированные по дате"""
    if not MIGRATION_PATH.exists():
        return []
    return sorted([f.stem for f in MIGRATION_PATH.glob("*.sql")])


def apply_migration(conn: sqlite3.Connection, name: str) -> None:
    """Находит файл по имени и выполняет его содержимое"""
    conn.executescript((MIGRATION_PATH / f"{name}.sql").read_text(encoding="utf-8"))
