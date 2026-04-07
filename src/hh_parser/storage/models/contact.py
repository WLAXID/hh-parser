from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from hh_parser.storage.models.base import BaseModel


@dataclass
class ContactModel(BaseModel):
    """Модель контакта работодателя."""

    id: int | None = None
    employer_id: int = 0
    employer_name: str = ""
    contact_type: Literal["email", "phone"] = "email"
    value: str = ""
    source: Literal["api", "site"] = "api"
    source_url: str | None = None
    normalized_value: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def email(self) -> str | None:
        """Возвращает значение, если это email, иначе None."""
        return self.value if self.contact_type == "email" else None

    @property
    def phone(self) -> str | None:
        """Возвращает значение, если это телефон, иначе None."""
        return self.value if self.contact_type == "phone" else None
