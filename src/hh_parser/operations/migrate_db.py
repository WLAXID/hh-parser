"""
CLI-команда для миграции базы данных.
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from hh_parser.main import BaseOperation
from hh_parser.storage.utils import (
    MIGRATION_PATH,
    QUERIES_PATH,
    apply_migration,
    init_db,
    list_migrations,
)

if TYPE_CHECKING:
    from hh_parser.main import HHParserTool

logger = logging.getLogger(__name__)


def remove_sql_comments(sql: str) -> str:
    """Удаляет SQL комментарии из строки."""
    # Удаляем однострочные комментарии --
    sql = re.sub(r"--[^\n]*", "", sql)
    # Удаляем многострочные комментарии /* */
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def parse_create_table(sql: str) -> dict:
    """Парсит CREATE TABLE и извлекает информацию о колонках и ограничениях."""
    result = {
        "columns": {},
        "foreign_keys": [],
        "checks": [],
        "column_order": [],  # Порядок колонок
    }

    # Удаляем комментарии перед парсингом
    sql = remove_sql_comments(sql)

    # Находим содержимое внутри CREATE TABLE
    # Ищем от CREATE TABLE до последней закрывающей скобки перед ; или концом
    match = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.+)\)",
        sql,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return result

    table_content = match.group(2)

    # Разбиваем на отдельные определения
    parts = []
    current = ""
    paren_depth = 0

    for char in table_content:
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "," and paren_depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current.strip())

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # FOREIGN KEY
        fk_match = re.match(
            r"FOREIGN\s+KEY\s*\((\w+)\)\s+REFERENCES\s+(\w+)\s*\((\w+)\)(?:\s+ON\s+DELETE\s+(\w+(?:\s+\w+)?))?",
            part,
            re.IGNORECASE,
        )
        if fk_match:
            result["foreign_keys"].append(
                {
                    "column": fk_match.group(1),
                    "ref_table": fk_match.group(2),
                    "ref_column": fk_match.group(3),
                    "on_delete": fk_match.group(4) if fk_match.group(4) else None,
                }
            )
            continue

        # CHECK constraint
        if part.upper().startswith("CHECK"):
            result["checks"].append(part)
            continue

        # PRIMARY KEY (отдельный)
        if part.upper().startswith("PRIMARY KEY"):
            continue

        # Обычная колонка
        # Тип может содержать скобки, например TEXT, INTEGER, VARCHAR(255)
        col_match = re.match(
            r"(\w+)\s+(\w+(?:\s*\([^)]*\))?)",
            part,
            re.IGNORECASE,
        )
        if col_match:
            col_name = col_match.group(1)
            col_type = col_match.group(2).strip()

            # Извлекаем дополнительные атрибуты
            col_def = {
                "type": col_type,
                "not_null": "NOT NULL" in part.upper(),
                "primary_key": "PRIMARY KEY" in part.upper(),
                "default": None,
                "check": None,
            }

            # DEFAULT - ищем значение после DEFAULT
            default_match = re.search(
                r"DEFAULT\s+('[^']*'|\d+\.?\d*|CURRENT_\w+)",
                part,
                re.IGNORECASE,
            )
            if default_match:
                col_def["default"] = default_match.group(1)

            # CHECK для колонки
            check_match = re.search(r"CHECK\s*\(([^)]+)\)", part, re.IGNORECASE)
            if check_match:
                col_def["check"] = check_match.group(1)

            result["columns"][col_name] = col_def
            result["column_order"].append(col_name)

    return result


def get_table_schema(conn: sqlite3.Connection, table: str) -> dict:
    """Получает текущую схему таблицы из БД."""
    result = {
        "columns": {},
        "foreign_keys": [],
        "column_order": [],
    }

    # Получаем информацию о колонках
    cursor = conn.execute(f"PRAGMA table_info({table})")
    for row in cursor.fetchall():
        col_name = row[1]
        result["columns"][col_name] = {
            "type": row[2],
            "not_null": bool(row[3]),
            "primary_key": bool(row[5]),
            "default": row[4],
        }
        result["column_order"].append(col_name)

    # Получаем внешние ключи
    cursor = conn.execute(f"PRAGMA foreign_key_list({table})")
    for row in cursor.fetchall():
        result["foreign_keys"].append(
            {
                "column": row[3],
                "ref_table": row[2],
                "ref_column": row[4],
                "on_delete": row[6] if len(row) > 6 else None,
            }
        )

    return result


def get_sql_tables(sql_path: Path) -> dict[str, str]:
    """Извлекает все CREATE TABLE из SQL-файла."""
    content = sql_path.read_text(encoding="utf-8")
    tables = {}

    # Находим все CREATE TABLE
    pattern = r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\([^;]+\);?"
    for match in re.finditer(pattern, content, re.DOTALL | re.IGNORECASE):
        table_name = match.group(1)
        tables[table_name] = match.group(0)

    return tables


def schemas_match(current: dict, expected: dict) -> bool:
    """Проверяет, совпадают ли схемы (порядок колонок важен)."""
    # Проверяем порядок колонок
    if current["column_order"] != expected["column_order"]:
        return False

    # Проверяем количество колонок
    if set(current["columns"].keys()) != set(expected["columns"].keys()):
        return False

    # Проверяем типы колонок
    for col_name, col_def in expected["columns"].items():
        current_col = current["columns"].get(col_name)
        if not current_col:
            return False
        # Сравниваем тип (без учёта регистра)
        if current_col["type"].upper() != col_def["type"].upper():
            return False

    return True


def get_default_value(col_def: dict) -> str:
    """Возвращает DEFAULT значение для колонки или подходящее значение по умолчанию."""
    if col_def.get("default") is not None:
        return col_def["default"]

    # Для NOT NULL колонок без DEFAULT возвращаем подходящее значение по типу
    col_type = col_def.get("type", "TEXT").upper()
    if "INT" in col_type:
        return "0"
    elif "REAL" in col_type or "FLOAT" in col_type or "DOUBLE" in col_type:
        return "0.0"
    else:
        # TEXT и другие типы - возвращаем NULL для nullable полей
        return "NULL"


def recreate_table_with_data(
    conn: sqlite3.Connection, table: str, create_sql: str, expected_schema: dict
) -> list[str]:
    """Пересоздаёт таблицу с сохранением данных."""
    applied = []

    # Получаем текущие данные
    cursor = conn.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()
    current_columns = [desc[0] for desc in cursor.description]

    # Получаем список колонок из новой схемы
    new_columns = expected_schema["column_order"]

    # Удаляем старую таблицу и создаём новую
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.executescript(create_sql)
    applied.append(f"DROP TABLE {table}")
    applied.append(f"CREATE TABLE {table}")

    # Если есть данные, переносим их
    if rows:
        # Определяем колонки для вставки
        # Для колонок, которые есть в обеих схемах - берём значения из данных
        # Для новых колонок - используем DEFAULT значения
        insert_columns = []
        for col in new_columns:
            insert_columns.append(col)

        # Формируем INSERT с явными значениями для всех колонок
        cols_str = ", ".join(insert_columns)

        # Создаём список значений для вставки
        for row in rows:
            row_dict = dict(zip(current_columns, row))
            values = []
            for col in insert_columns:
                if col in current_columns:
                    # Берём значение из существующих данных
                    values.append(row_dict.get(col))
                else:
                    # Для новой колонки используем DEFAULT значение
                    col_def = expected_schema["columns"].get(col, {})
                    default_val = get_default_value(col_def)
                    # Вставляем как есть (строка или число)
                    values.append(default_val)

            placeholders = ", ".join(["?"] * len(values))
            conn.execute(
                f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})", values
            )

        applied.append(f"COPY {len(rows)} rows to new table")

    return applied


def auto_migrate(conn: sqlite3.Connection) -> list[str]:
    """Автоматически применяет миграции, сравнивая схему из SQL-файлов с БД."""
    applied = []

    # Получаем список SQL-файлов со схемами
    schema_files = [
        QUERIES_PATH / "schema.sql",
        QUERIES_PATH / "schema_contacts.sql",
    ]

    for schema_file in schema_files:
        if not schema_file.exists():
            continue

        tables_sql = get_sql_tables(schema_file)

        for table_name, create_sql in tables_sql.items():
            # Проверяем существование таблицы
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            table_exists = cursor.fetchone() is not None

            if not table_exists:
                # Таблица не существует — создаём
                logger.info(f"Создание таблицы {table_name}")
                conn.executescript(create_sql)
                applied.append(f"CREATE TABLE {table_name}")
                continue

            # Таблица существует — проверяем различия
            current_schema = get_table_schema(conn, table_name)
            expected_schema = parse_create_table(create_sql)

            # Проверяем, совпадают ли схемы
            if schemas_match(current_schema, expected_schema):
                # Схемы совпадают, пропускаем
                continue

            # Схемы различаются — нужно мигрировать
            logger.info(f"Миграция таблицы {table_name}")

            # Проверяем, есть ли новые колонки или изменён порядок
            current_cols = set(current_schema["columns"].keys())
            expected_cols = set(expected_schema["columns"].keys())

            # Если есть колонки в текущей таблице, которых нет в ожидаемой — это ошибка
            extra_cols = current_cols - expected_cols
            if extra_cols:
                logger.warning(
                    f"Таблица {table_name} имеет лишние колонки: {extra_cols}"
                )

            # Пересоздаём таблицу с сохранением данных
            changes = recreate_table_with_data(
                conn, table_name, create_sql, expected_schema
            )
            applied.extend(changes)

    # Применяем индексы и триггеры из схем
    for schema_file in schema_files:
        if not schema_file.exists():
            continue

        content = schema_file.read_text(encoding="utf-8")

        # CREATE INDEX
        for match in re.finditer(
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)",
            content,
            re.IGNORECASE,
        ):
            index_name = match.group(1)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (index_name,),
            )
            if not cursor.fetchone():
                # Индекс не существует — выполняем весь CREATE INDEX
                idx_match = re.search(
                    rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+{index_name}[^;]+;",
                    content,
                    re.IGNORECASE,
                )
                if idx_match:
                    conn.execute(idx_match.group(0))
                    applied.append(f"CREATE INDEX {index_name}")

        # CREATE TRIGGER
        for match in re.finditer(
            r"CREATE\s+TRIGGER\s+IF\s+NOT\s+EXISTS\s+(\w+)",
            content,
            re.IGNORECASE,
        ):
            trigger_name = match.group(1)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name=?",
                (trigger_name,),
            )
            if not cursor.fetchone():
                # Триггер не существует — находим и выполняем
                # Триггеры могут содержать несколько statements, поэтому ищем до END;
                trig_match = re.search(
                    rf"CREATE\s+TRIGGER\s+IF\s+NOT\s+EXISTS\s+{trigger_name}[\s\S]*?END;",
                    content,
                    re.IGNORECASE,
                )
                if trig_match:
                    conn.execute(trig_match.group(0))
                    applied.append(f"CREATE TRIGGER {trigger_name}")

    return applied


class Operation(BaseOperation):
    """Миграция схемы базы данных."""

    __aliases__: list = ["migrate"]

    def setup_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--list",
            action="store_true",
            help="Показать список доступных миграций",
        )
        parser.add_argument(
            "--apply",
            nargs="?",
            const=None,
            metavar="NAME",
            help="Без аргумента: применить автоматические миграции. С аргументом: применить конкретную миграцию из директории migrations",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Показать статус базы данных (таблицы, индексы)",
        )

    def run(self, tool: "HHParserTool", args) -> int | None:
        db_path = tool.db_path

        # Если просто показать список миграций
        if args.list:
            migrations = list_migrations()
            if not migrations:
                print("Файловые миграции не найдены.")
                if MIGRATION_PATH.exists():
                    print(f"Директория миграций: {MIGRATION_PATH}")
                else:
                    print(f"Директория миграций не существует: {MIGRATION_PATH}")
            else:
                print(f"Доступные миграции ({len(migrations)}):")
                for m in migrations:
                    print(f"  - {m}")
            print()
            print("Примечание: используйте --apply для автоматической миграции схемы")
            return 0

        # Показать статус базы данных
        if args.status:
            return self._show_status(db_path)

        # Применить миграцию
        if args.apply is not None:
            # Если передано имя миграции — применить конкретную
            if args.apply:
                return self._apply_file_migration(db_path, args.apply)
            # Если --apply без аргумента — автоматическая миграция
            else:
                return self._auto_migrate(db_path)

        # Если нет аргументов — показать справку
        print(
            "Используйте --apply для автоматической миграции или --status для проверки."
        )
        print("Примеры:")
        print(" hh-parser migrate-db --apply # применить автоматические миграции")
        print(
            " hh-parser migrate-db --apply 2026-04-04_set_contacts_status_default # применить конкретную миграцию"
        )
        print(" hh-parser migrate-db --status # показать статус БД")
        print(" hh-parser migrate-db --list # показать файловые миграции")
        return 0

    def _show_status(self, db_path) -> int:
        """Показать статус базы данных."""
        print(f"База данных: {db_path}")
        print()

        if not db_path.exists():
            print("База данных не существует.")
            return 1

        conn = sqlite3.connect(str(db_path))
        try:
            # Таблицы
            print("Таблицы:")
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = cursor.fetchall()
            for (name,) in tables:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {name}")
                count = cursor.fetchone()[0]
                print(f"  - {name}: {count} записей")

                # Показываем колонки
                cursor = conn.execute(f"PRAGMA table_info({name})")
                cols = cursor.fetchall()
                for col in cols:
                    col_name = col[1]
                    col_type = col[2]
                    not_null = "NOT NULL" if col[3] else ""
                    default = f"DEFAULT {col[4]}" if col[4] else ""
                    pk = "PRIMARY KEY" if col[5] else ""
                    attrs = " ".join(x for x in [col_type, not_null, default, pk] if x)
                    print(f"      {col_name}: {attrs}")
            print()

            # Индексы
            print("Индексы:")
            cursor = conn.execute(
                "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            indexes = cursor.fetchall()
            for name, tbl_name in indexes:
                print(f"  - {name} (таблица: {tbl_name})")
            print()

            # Триггеры
            print("Триггеры:")
            cursor = conn.execute(
                "SELECT name, tbl_name FROM sqlite_master WHERE type='trigger' ORDER BY name"
            )
            triggers = cursor.fetchall()
            if triggers:
                for name, tbl_name in triggers:
                    print(f"  - {name} (таблица: {tbl_name})")
            else:
                print("  (нет триггеров)")

        finally:
            conn.close()

        return 0

    def _auto_migrate(self, db_path) -> int:
        """Применить автоматические миграции."""
        # Создаём директорию для БД если не существует
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        try:
            print(f"Автоматическая миграция БД: {db_path}")

            # Сначала применяем базовую схему
            init_db(conn)
            conn.commit()

            # Затем применяем автоматические миграции
            applied = auto_migrate(conn)
            conn.commit()

            if applied:
                print(f"Применено {len(applied)} изменений:")
                for change in applied:
                    print(f"  [OK] {change}")
            else:
                print("Схема БД актуальна, изменений не требуется.")

            return 0

        except Exception as e:
            logger.exception("Ошибка миграции")
            print(f"Ошибка: {e}")
            conn.rollback()
            return 1
        finally:
            conn.close()

    def _apply_file_migration(self, db_path, name: str) -> int:
        """Применить конкретную миграцию из файла."""
        migrations = list_migrations()
        if name not in migrations:
            print(f"Ошибка: миграция '{name}' не найдена.")
            print(
                f"Доступные миграции: {', '.join(migrations) if migrations else 'нет'}"
            )
            return 1

        conn = sqlite3.connect(str(db_path))
        try:
            print(f"Применение миграции: {name}")
            apply_migration(conn, name)
            conn.commit()
            print(f"[OK] Миграция {name} применена успешно.")
            return 0
        except Exception as e:
            print(f"[ERROR] Ошибка при применении {name}: {e}")
            conn.rollback()
            return 1
        finally:
            conn.close()
