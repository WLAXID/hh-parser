from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from hh_parser.storage.models.base import BaseModel, mapped


@dataclass
class EmployerModel(BaseModel):
    id: int                          # ID работодателя
    name: str                        # Название компании
    site_url: str | None = None      # Официальный сайт
    alternate_url: str | None = None # Страница на hh.ru
    open_vacancies: int = 0          # Количество открытых вакансий
    total_responses: int = 0         # Суммарное количество откликов
    avg_responses: float = 0.0       # Среднее количество откликов на вакансию
    industries: str | None = None    # Отрасли (JSON)
    area_name: str | None = None     # Регион
    created_at: datetime | None = None
    updated_at: datetime | None = None