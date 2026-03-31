from __future__ import annotations

from hh_parser.storage.models.vacancy import VacancyModel
from .base import BaseRepository


class VacanciesRepository(BaseRepository):
    __table__ = "vacancies"
    model = VacancyModel