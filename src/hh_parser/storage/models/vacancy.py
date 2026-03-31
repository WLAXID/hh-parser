from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from hh_parser.storage.models.base import BaseModel


@dataclass
class VacancyModel(BaseModel):
    id: int
    employer_id: int
    name: str | None = None
    responses_count: int = 0
    total_responses: int = 0
    created_at: datetime | None = None