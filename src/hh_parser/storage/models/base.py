import builtins
from dataclasses import Field, asdict, dataclass, field, fields
from datetime import datetime
from logging import getLogger
from typing import Any, Callable, Mapping, Self, dataclass_transform, get_origin

from hh_parser.utils import json
from hh_parser.utils.date import try_parse_datetime

logger = getLogger(__package__)

MISSING = object()


def mapped(
    *,
    skip_src: bool = False,
    path: str | None = None,
    transform: Callable[[Any], Any] | None = None,
    store_json: bool = False,
    **kwargs: Any,
):
    metadata = kwargs.get("metadata", {})
    metadata.setdefault("skip_src", skip_src)
    metadata.setdefault("path", path)
    metadata.setdefault("transform", transform)
    metadata.setdefault("store_json", store_json)
    return field(metadata=metadata, **kwargs)


@dataclass_transform(field_specifiers=(field, mapped))
class BaseModel:
    def __init_subclass__(cls, /, **kwargs: Any):
        super().__init_subclass__()
        dataclass(cls, kw_only=True, **kwargs)

    @classmethod
    def from_db(cls, data: Mapping[str, Any]) -> Self:
        return cls._from_mapping(data)

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> Self:
        return cls._from_mapping(data, from_source=True)

    def to_db(self) -> dict[str, Any]:
        data = self.to_dict()
        for f in fields(self):
            value = data.get(f.name, MISSING)
            if value is MISSING:
                continue
            if f.metadata.get("store_json"):
                value = json.dumps(value)

            data[f.name] = value
        return data

    @classmethod
    def _coerce_type(cls, value: Any, f: Field) -> Any:
        if get_origin(f.type):
            return value

        type_name = f.type if isinstance(f.type, str) else f.type.__name__
        if value is not None and type_name in (
            "bool",
            "str",
            "int",
            "float",
            "datetime",
        ):
            if type_name == "datetime":
                return try_parse_datetime(value)
            try:
                t = getattr(builtins, type_name)
                if not isinstance(value, t):
                    value = t(value)
            except (TypeError, ValueError):
                pass
        return value

    @classmethod
    def _from_mapping(
        cls, data: Mapping[str, Any], /, from_source: bool = False
    ) -> Self:
        kwargs = {}
        for f in fields(cls):
            # Пропускаем поле, если оно помечено как skip_src при импорте из API
            if from_source and f.metadata.get("skip_src") and f.name in data:
                continue

            # Получаем значение поля
            if from_source and (path := f.metadata.get("path")):
                # Извлечение значения по пути (например, "location.city.name")
                v = data
                found = True
                for key in path.split("."):
                    if isinstance(v, Mapping):
                        v = v.get(key)
                    else:
                        found = False
                        break
                if not found:
                    continue
                value = v
            else:
                value = data.get(f.name, MISSING)

            if value is MISSING:
                continue

            # Применяем трансформацию, если указана
            if value is not None and (t := f.metadata.get("transform")):
                if isinstance(t, str):
                    t = getattr(cls, t)
                value = t(value)

            # Обрабатываем JSON-поля
            if f.metadata.get("store_json"):
                if isinstance(value, str):
                    value = json.loads(value)

            value = cls._coerce_type(value, f)

            kwargs[f.name] = value
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


if __name__ == "__main__":

    class CompanyModel(BaseModel):
        id: "int"
        name: str
        city_id: int = mapped(path="location.city.id")
        city: str = mapped(path="location.city.name")
        created_at: datetime

    c = CompanyModel.from_api(
        {
            "id": "42",
            "name": "ACME",
            "location": {
                "city": {
                    "id": "1",
                    "name": "Moscow",
                },
            },
            "created_at": "2026-01-09T04:12:00.114858",
        }
    )

    print(c)
