"""
Операции бизнес-логики.

Каждый модуль содержит класс Operation для выполнения
соответствующей бизнес-операции.
"""

from .authorize import Operation as AuthorizeOperation
from .export import ExportContactsOperation, ExportEmployersOperation
from .migrate_db import Operation as MigrateDbOperation
from .parse import Operation as ParseOperation
from .parse_contacts import Operation as ParseContactsOperation

__all__ = (
    "AuthorizeOperation",
    "MigrateDbOperation",
    "ParseOperation",
    "ParseContactsOperation",
    "ExportEmployersOperation",
    "ExportContactsOperation",
)
