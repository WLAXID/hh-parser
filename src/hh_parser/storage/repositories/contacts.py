from __future__ import annotations

import logging
from typing import Iterator

from hh_parser.storage.models.contact import ContactModel

from .base import BaseRepository

logger = logging.getLogger(__name__)


class ContactsRepository(BaseRepository):
    """Репозиторий для работы с контактами работодателей."""

    __table__ = "contacts"
    model = ContactModel

    def find(self, **kwargs) -> Iterator[ContactModel]:
        """Найти контакты по критериям."""
        return super().find(**kwargs)

    def find_by_employer(self, employer_id: int) -> Iterator[ContactModel]:
        """Найти все контакты работодателя."""
        return self.find(employer_id=employer_id)

    def exists(self, contact_type: str, normalized_value: str) -> bool:
        """Проверить существование контакта (глобально по всем работодателям)."""
        cursor = self.conn.execute(
            """
            SELECT 1 FROM contacts
            WHERE contact_type = ? AND normalized_value = ?
            LIMIT 1
            """,
            (contact_type, normalized_value),
        )
        return cursor.fetchone() is not None

    def save(self, contact: ContactModel) -> ContactModel:
        """Сохранить контакт (вставка или обновление)."""
        # Проверяем существование по уникальному ключу (глобально)
        if self.exists(contact.contact_type, contact.normalized_value):
            # Обновление существующего контакта
            self.conn.execute(
                """
                UPDATE contacts SET
                    employer_id = ?,
                    employer_name = ?,
                    value = ?,
                    source = ?,
                    source_url = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE contact_type = ? AND normalized_value = ?
                """,
                (
                    contact.employer_id,
                    contact.employer_name,
                    contact.value,
                    contact.source,
                    contact.source_url,
                    contact.contact_type,
                    contact.normalized_value,
                ),
            )
        else:
            # Вставка нового контакта
            cursor = self.conn.execute(
                """
                INSERT INTO contacts (employer_id, employer_name, contact_type, value, source, source_url, normalized_value)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contact.employer_id,
                    contact.employer_name,
                    contact.contact_type,
                    contact.value,
                    contact.source,
                    contact.source_url,
                    contact.normalized_value,
                ),
            )
            contact.id = cursor.lastrowid

        self.conn.commit()
        return contact

    def save_many(self, contacts: list[ContactModel]) -> int:
        """Сохранить несколько контактов. Возвращает количество сохранённых."""
        saved = 0
        for contact in contacts:
            try:
                self.save(contact)
                saved += 1
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.warning(f"Ошибка сохранения контакта {contact}: {e}")
        return saved

    def delete_by_employer(self, employer_id: int) -> int:
        """Удалить все контакты работодателя."""
        cursor = self.conn.execute(
            "DELETE FROM contacts WHERE employer_id = ?", (employer_id,)
        )
        self.conn.commit()
        return cursor.rowcount

    def count_by_employer(self, employer_id: int) -> int:
        """Подсчитать количество контактов работодателя."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE employer_id = ?", (employer_id,)
        )
        return cursor.fetchone()[0]
