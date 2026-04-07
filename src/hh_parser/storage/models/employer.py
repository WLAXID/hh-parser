from dataclasses import dataclass
from datetime import datetime

from hh_parser.storage.models.base import BaseModel


@dataclass
class EmployerModel(BaseModel):
    id: int
    name: str
    contacts_status: str = "not_checked"
    site_url: str | None = None
    alternate_url: str | None = None
    open_vacancies: int = 0
    total_responses: int = 0
    avg_responses: float = 0.0
    industries: str | None = None
    area_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
