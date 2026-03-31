from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from hh_parser.storage.models.base import BaseModel


@dataclass
class ContactModel(BaseModel):
    """Модель контакта работодателя."""

    id: int | None = None
    employer_id: int = 0
    employer_name: str = ""  # Название работодателя как на hh.ru
    contact_type: Literal["email", "phone"] = "email"
    value: str = ""
    source: Literal["api", "site"] = "api"
    source_url: str | None = None
    normalized_value: str = ""
    created_at: datetime | None = None
