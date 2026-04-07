"""Бизнес-логика парсера hh.ru.

Этот модуль содержит класс HHParserTool для работы с API hh.ru,
управления конфигурацией, токенами и базой данных.
"""

from __future__ import annotations

import logging
import sqlite3
from functools import cached_property
from http.cookiejar import MozillaCookieJar
from os import getenv
from pathlib import Path

import requests
import urllib3

from . import api, storage
from .utils.cookiejar import HHOnlyCookieJar

# Отключаем предупреждения urllib3 о небезопасных соединениях
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__package__)


class HHParserTool:
    """Утилита для сбора данных о работодателях с сайта hh.ru."""

    def __init__(self):
        # Значения по умолчанию для атрибутов
        self.config_dir: Path | None = None
        self.profile_id: str | None = None
        self.verbosity: int = 0
        self.api_delay: float | None = None
        self.user_agent: str | None = None

    @cached_property
    def session(self) -> requests.Session:
        session = requests.Session()
        session.verify = False
        session.cookies = HHOnlyCookieJar(str(self.cookies_file))
        if self.cookies_file.exists():
            session.cookies.load(ignore_discard=True, ignore_expires=True)
        return session

    @cached_property
    def config_path(self) -> Path:
        # Определяем базовую директорию конфигурации
        # Приоритет: --config-dir, CONFIG_DIR, cwd/data
        if self.config_dir:
            base_dir = self.config_dir
        else:
            config_dir_env = getenv("CONFIG_DIR", "")
            base_dir = Path(config_dir_env) if config_dir_env else Path.cwd() / "data"

        # Определяем имя профиля
        profile = self.profile_id or getenv("HH_PROFILE_ID", "default")

        return (base_dir / profile).resolve()

    @cached_property
    def config(self) -> dict:
        config_file = self.config_path / "config.json"
        if config_file.exists():
            import json

            return json.loads(config_file.read_text(encoding="utf-8"))
        return {}

    @cached_property
    def log_file(self) -> Path:
        return self.config_path / "hh_parser.log"

    @cached_property
    def cookies_file(self) -> Path:
        return self.config_path / "cookies.txt"

    @cached_property
    def db_path(self) -> Path:
        return self.config_path / "hh_parser.db"

    @cached_property
    def db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        return conn

    @cached_property
    def storage(self) -> storage.StorageFacade:
        return storage.StorageFacade(self.db)

    @cached_property
    def api_client(self) -> api.client.ApiClient:
        token = self.config.get("token", {})
        return api.client.ApiClient(
            client_id=self.config.get("client_id"),
            client_secret=self.config.get("client_secret"),
            access_token=token.get("access_token"),
            refresh_token=token.get("refresh_token"),
            access_expires_at=token.get("access_expires_at"),
            delay=self.api_delay or self.config.get("api_delay"),
            user_agent=self.user_agent or self.config.get("user_agent"),
            session=self.session,
        )

    def save_token(self) -> bool:
        if self.api_client.access_token != self.config.get("token", {}).get(
            "access_token"
        ):
            self.config["token"] = self.api_client.get_access_token()
            import json

            self.config_path.mkdir(parents=True, exist_ok=True)
            (self.config_path / "config.json").write_text(
                json.dumps(self.config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        return False

    def save_cookies(self) -> None:
        """Сохраняет текущие куки сессии в файл."""
        if isinstance(self.session.cookies, MozillaCookieJar):
            self.session.cookies.save(ignore_discard=True, ignore_expires=True)
            logger.debug("Cookies saved to %s", self.cookies_file)
        else:
            logger.warning(
                f"Сессионные куки имеют неправильный тип: {type(self.session.cookies)}"
            )
