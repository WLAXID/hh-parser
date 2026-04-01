from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from collections.abc import Sequence
from functools import cached_property
from http.cookiejar import MozillaCookieJar
from importlib import import_module
from os import getenv
from pathlib import Path
from pkgutil import iter_modules
from typing import Callable

import requests
import urllib3

from . import api, storage
from .utils import setup_terminal
from .utils.cookiejar import HHOnlyCookieJar
from .utils.log import setup_logger

logger = logging.getLogger(__package__)

OPERATIONS = "operations"


class BaseOperation:
    def setup_parser(self, parser: argparse.ArgumentParser) -> None: ...

    def run(
        self,
        tool: "HHParserTool",
        args: BaseNamespace,
    ) -> None | int:
        raise NotImplementedError()


class BaseNamespace(argparse.Namespace):
    profile_id: str
    config_dir: Path
    verbosity: int
    api_delay: float
    user_agent: str
    operation_run: Callable[["HHParserTool", BaseNamespace], None | int] | None


class HHParserTool:
    """Утилита для сбора данных о работодателях с сайта hh.ru."""

    class ArgumentFormatter(
        argparse.ArgumentDefaultsHelpFormatter,
        argparse.RawDescriptionHelpFormatter,
    ):
        pass

    @classmethod
    def _create_parser(cls) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description=cls.__doc__,
            formatter_class=cls.ArgumentFormatter,
        )
        parser.add_argument(
            "-v",
            "--verbosity",
            help="При использовании от одного и более раз увеличивает количество отладочной информации в выводе",
            action="count",
            default=0,
        )
        parser.add_argument(
            "-c",
            "--config-dir",
            "--config",
            help="Путь до директории с конфигом",
            type=Path,
            default=None,
        )
        parser.add_argument(
            "--profile-id",
            "--profile",
            help="Используемый профиль — подкаталог в --config-dir. Так же можно передать через переменную окружения HH_PROFILE_ID.",
        )
        parser.add_argument(
            "-d",
            "--api-delay",
            "--delay",
            type=float,
            help="Задержка между запросами к API HH по умолчанию",
        )
        parser.add_argument(
            "--user-agent",
            help="User-Agent для каждого запроса",
        )

        subparsers = parser.add_subparsers(help="commands")

        package_dir = Path(__file__).resolve().parent / OPERATIONS
        for _, module_name, _ in iter_modules([str(package_dir)]):
            if module_name.startswith("_"):
                continue
            mod = import_module(f"{__package__}.{OPERATIONS}.{module_name}")
            op: BaseOperation = mod.Operation()
            kebab_name = module_name.replace("_", "-")
            op_parser = subparsers.add_parser(
                kebab_name,
                aliases=getattr(op, "__aliases__", []),
                description=op.__doc__,
                formatter_class=cls.ArgumentFormatter,
            )
            op_parser.set_defaults(operation_run=op.run)
            op.setup_parser(op_parser)

        parser.set_defaults(operation_run=None)
        return parser

    def __init__(self):
        self._parser = self._create_parser()
        # Значения по умолчанию для атрибутов, устанавливаемых через _assign_args
        self.config_dir: Path | None = None
        self.profile_id: str | None = None

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

    def run(self, argv: Sequence[str] | None = None) -> None | int:
        args = self._parser.parse_args(argv, namespace=BaseNamespace())
        self._assign_args(args)

        # Создаем путь до конфига
        self.config_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        # По умолчанию выводим INFO и выше, -v включает DEBUG
        verbosity_level = max(
            logging.DEBUG,
            logging.INFO - self.verbosity * 10,
        )

        setup_logger(logger, verbosity_level, self.log_file)

        logger.debug("Путь до профиля: %s", self.config_path)

        setup_terminal()

        try:
            if self.operation_run:
                try:
                    return self.operation_run(self, args)
                except KeyboardInterrupt:
                    logger.warning("Выполнение прервано пользователем!")
                except api.errors.InternalServerError:
                    logger.error(
                        "Сервер HH.RU не смог обработать запрос из-за высокой"
                        " нагрузки или по иной причине"
                    )
                except api.errors.Forbidden:
                    logger.error("Требуется авторизация")
                except ValueError as ex:
                    logger.error(ex)
                except sqlite3.Error as ex:
                    logger.exception(ex)
                    script_name = sys.argv[0].split(os.sep)[-1]
                    logger.warning(
                        f"Возможно база данных повреждена, попробуйте выполнить команду:\n\n"
                        f" {script_name} migrate-db"
                    )
                return 1
            self._parser.print_help(file=sys.stderr)
            return 2
        except Exception as e:
            logger.exception(e)
            return 1
        finally:
            # Токен мог автоматически обновиться
            if self.save_token():
                logger.info("Токен был сохранен после обновления.")
            try:
                self.save_cookies()
            except Exception as ex:
                logger.error(f"Не удалось сохранить cookies: {ex}")

    def _assign_args(self, args: BaseNamespace) -> None:
        for name, value in vars(args).items():
            setattr(self, name, value)


def main(argv: Sequence[str] | None = None) -> None | int:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return HHParserTool().run(argv)


if __name__ == "__main__":
    sys.exit(main())
