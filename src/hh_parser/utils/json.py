"""JSON утилиты с поддержкой datetime."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any


class JSONEncoder(json.JSONEncoder):
    """JSON encoder с поддержкой datetime."""

    def default(self, o):
        if isinstance(o, dt.datetime):
            return int(o.timestamp())
        return super().default(o)


class JSONDecoder(json.JSONDecoder):
    """JSON decoder."""

    pass


def dumps(obj, *args: Any, **kwargs: Any) -> str:
    """Сериализует объект в JSON строку."""
    kwargs.setdefault("cls", JSONEncoder)
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(obj, *args, **kwargs)


def dump(obj, fp, *args: Any, **kwargs: Any) -> None:
    """Сериализует объект в файл."""
    kwargs.setdefault("cls", JSONEncoder)
    kwargs.setdefault("ensure_ascii", False)
    json.dump(obj, fp, *args, **kwargs)


def loads(s, *args: Any, **kwargs: Any) -> Any:
    """Десериализует JSON строку в объект."""
    return json.loads(s, *args, **kwargs)


def load(fp, *args: Any, **kwargs: Any) -> Any:
    """Десериализует JSON из файла."""
    return json.load(fp, *args, **kwargs)


if __name__ == "__main__":
    d = {"created_at": dt.datetime.now()}
    print(loads(dumps(d)))
