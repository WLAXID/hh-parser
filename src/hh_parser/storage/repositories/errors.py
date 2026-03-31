"""Ошибки репозиториев и декоратор для обработки ошибок БД."""

from __future__ import annotations

import logging
import sqlite3
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__package__)

T = TypeVar("T")


class DatabaseError(Exception):
    """Базовая ошибка базы данных."""

    pass


class RecordNotFoundError(DatabaseError):
    """Запись не найдена."""

    pass


class UniqueConstraintError(DatabaseError):
    """Нарушение уникального ограничения."""

    pass


class ForeignKeyError(DatabaseError):
    """Нарушение внешнего ключа."""

    pass


def wrap_db_errors(func: Callable[..., T]) -> Callable[..., T]:
    """Декоратор для обёртки ошибок SQLite в DatabaseError."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return func(*args, **kwargs)
        except sqlite3.IntegrityError as e:
            error_msg = str(e).lower()
            if "unique" in error_msg:
                raise UniqueConstraintError(str(e)) from e
            elif "foreign key" in error_msg:
                raise ForeignKeyError(str(e)) from e
            raise DatabaseError(str(e)) from e
        except sqlite3.Error as e:
            logger.error("Database error: %s", e)
            raise DatabaseError(str(e)) from e

    return wrapper
