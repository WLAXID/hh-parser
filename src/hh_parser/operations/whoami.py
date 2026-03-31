from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING

from ..api.client import ApiClient
from ..main import BaseOperation

if TYPE_CHECKING:
    from ..main import HHParserTool

logger = logging.getLogger(__name__)


class Operation(BaseOperation):
    """Показать информацию о текущем пользователе"""

    __aliases__: list = ["whoami"]

    def setup_parser(self, parser: argparse.ArgumentParser) -> None:
        # Нет аргументов
        pass

    def run(self, tool: "HHParserTool", args) -> int | None:
        api_client: ApiClient = tool.api_client
        try:
            user = api_client.get("/me")
            # Выводим информацию о пользователе в удобочитаемом виде
            print("Информация о текущем пользователе:")
            print(f"  ID: {user.get('id')}")
            print(f"  Имя: {user.get('first_name')} {user.get('last_name')}")
            if user.get("middle_name"):
                print(f"  Отчество: {user.get('middle_name')}")
            print(f"  Email: {user.get('email')}")
            print(f"  Телефон: {user.get('phone')}")
            print(f"  Является соискателем: {user.get('is_applicant')}")
            print(f"  Является работодателем: {user.get('is_employer')}")
            print(f"  Является администратором: {user.get('is_admin')}")
        except Exception as e:
            logger.error(f"Не удалось получить информацию о пользователе: {e}")
            return 1
        return 0
