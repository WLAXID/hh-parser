from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__package__)


class SettingsRepository:
    """Репозиторий для хранения настроек в БД."""

    __table__ = "settings"

    def __init__(self, conn: sqlite3.Connection, auto_commit: bool = True):
        self.conn = conn
        self.auto_commit = auto_commit

    def _ensure_table(self) -> None:
        """Создает таблицу настроек, если она не существует."""
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.__table__} (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

    def get_value(self, key: str, default: Any = None) -> Any:
        """Получает значение настройки по ключу."""
        self._ensure_table()
        cur = self.conn.execute(
            f"SELECT value FROM {self.__table__} WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return row[0]

    def set_value(self, key: str, value: Any, commit: bool | None = None) -> None:
        """Устанавливает значение настройки."""
        self._ensure_table()
        if value is None:
            value_str = None
        elif isinstance(value, str):
            value_str = value
        else:
            value_str = json.dumps(value, ensure_ascii=False, default=str)

        self.conn.execute(
            f"""
            INSERT INTO {self.__table__} (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value_str),
        )

        if commit if commit is not None else self.auto_commit:
            self.conn.commit()
