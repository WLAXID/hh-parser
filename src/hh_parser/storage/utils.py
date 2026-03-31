from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

QUERIES_PATH: Path = Path(__file__).parent / "queries"
MIGRATION_PATH: Path = QUERIES_PATH / "migrations"


logger: logging.Logger = logging.getLogger(__package__)


def _parse_column_definitions(create_table_sql: str) -> dict[str, dict]:
    """Парсит определения колонок из CREATE TABLE SQL.

    Returns:
        Dict: {column_name: {"type": str, "not_null": bool, "default": str}}
    """
    columns = {}
    # Находим тело CREATE TABLE
    match = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+\w+\s*\((.*)\);",
        create_table_sql,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return columns

    body = match.group(1)
    # Разбиваем по запятым, но не внутри скобок
    parts = []
    depth = 0
    current = ""
    for char in body:
        if char == "(":
            depth += 1
            current += char
        elif char == ")":
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current.strip())

    for part in parts:
        part = part.strip()
        # Пропускаем FOREIGN KEY, PRIMARY KEY, CHECK, UNIQUE, INDEX
        if any(
            kw in part.upper()
            for kw in ["FOREIGN", "PRIMARY", "CHECK", "UNIQUE", "INDEX"]
        ):
            continue

        # Парсим колонку: name type [NOT NULL] [DEFAULT value]
        col_match = re.match(r"(\w+)\s+(\w+)(.*)", part, re.IGNORECASE)
        if col_match:
            col_name = col_match.group(1)
            col_type = col_match.group(2).upper()
            col_opts = col_match.group(3)

            not_null = "NOT NULL" in col_opts.upper()
            default = None
            default_match = re.search(r"DEFAULT\s+(\S+)", col_opts, re.IGNORECASE)
            if default_match:
                default = default_match.group(1)

            columns[col_name] = {
                "type": col_type,
                "not_null": not_null,
                "default": default,
            }

    return columns


def _add_missing_columns(
    conn: sqlite3.Connection, table: str, expected_columns: dict
) -> list[str]:
    """Добавляет недостающие колонки в существующую таблицу.

    Returns:
        List of applied changes descriptions.
    """
    applied = []

    # Получаем текущие колонки
    cursor = conn.execute(f"PRAGMA table_info({table})")
    existing_cols = {row[1]: row[2] for row in cursor.fetchall()}

    for col_name, col_def in expected_columns.items():
        if col_name in existing_cols:
            continue

        # Формируем ALTER TABLE ADD COLUMN
        sql_type = col_def["type"]
        not_null = col_def.get("not_null", False)
        default = col_def.get("default")

        alter_sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {sql_type}"
        if not_null and default is None:
            # SQLite требует DEFAULT для NOT NULL колонок при ALTER TABLE
            if sql_type in ("INTEGER", "REAL"):
                alter_sql += " DEFAULT 0"
            elif sql_type == "TEXT":
                alter_sql += " DEFAULT ''"

        logger.info(f"Добавление колонки {col_name} в таблицу {table}")
        conn.execute(alter_sql)
        applied.append(f"ADD COLUMN {col_name}")

    return applied


def init_db(conn: sqlite3.Connection) -> None:
    """Создает схему БД"""
    changes_before = conn.total_changes

    conn.executescript((QUERIES_PATH / "schema.sql").read_text(encoding="utf-8"))

    if conn.total_changes > changes_before:
        logger.info("Применена схема бд")

    # Применяем схему контактов
    schema_contacts_path = QUERIES_PATH / "schema_contacts.sql"
    if schema_contacts_path.exists():
        logger.debug(f"Применение схемы контактов из {schema_contacts_path}")

        # Проверяем текущую структуру таблицы contacts
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='contacts'"
        )
        table_exists = cursor.fetchone() is not None

        if table_exists:
            # Таблица существует - добавляем недостающие колонки
            expected_sql = schema_contacts_path.read_text(encoding="utf-8")
            expected_columns = _parse_column_definitions(expected_sql)

            if expected_columns:
                applied = _add_missing_columns(conn, "contacts", expected_columns)
                if applied:
                    logger.info(f"Добавлены колонки в contacts: {applied}")

        # Применяем схему (индексы и триггеры)
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
