"""
Модуль парсинга контактов с сайта работодателя.

Поддерживает два режима работы:
1. requests - быстрые HTTP-запросы (по умолчанию)
2. playwright - рендеринг JavaScript с возможностью headless/visible режима
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urljoin, urlparse

import requests
from requests.exceptions import RequestException

from hh_parser.storage.models.contact import ContactModel

from .extractors import extract_emails, extract_phones, normalize_email, normalize_phone

logger = logging.getLogger(__name__)


# ============================================================================
# Конфигурация парсера
# ============================================================================


@dataclass
class SiteParserConfig:
    """Конфигурация парсера сайта."""

    timeout: float = 30.0
    connect_timeout: float = 10.0
    delay_between_requests: float = 2.0
    max_redirects: int = 5
    max_pages_per_site: int = 10
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    # Playwright settings
    use_browser: bool = False
    headless: bool = True
    browser_timeout: float = 60000.0  # milliseconds for Playwright


DEFAULT_CONFIG = SiteParserConfig()


# ============================================================================
# Типовые URL для поиска контактов
# ============================================================================

CONTACT_URL_PATTERNS = [
    "/contacts",
    "/contact",
    "/about/contacts",
    "/about",
    "/company/contacts",
    "/company",
    "/ru/contacts",
    "/en/contacts",
    "/info/contacts",
    "/feedback",
    "/contact-us",
    "/about-us",
    "/about-us/contacts",
    "/o-kompanii",
    "/o-kompanii/kontakty",
    "/rekvizity",
]


# ============================================================================
# Ключевые слова для поиска ссылок
# ============================================================================

CONTACT_KEYWORDS_RU = [
    "контакты",
    "связаться с нами",
    "обратная связь",
    "написать нам",
    "позвонить нам",
    "наши контакты",
    "офис",
    "адрес",
    "телефон",
    "реквизиты",
]

CONTACT_KEYWORDS_EN = [
    "contact",
    "contacts",
    "contact us",
    "get in touch",
    "reach us",
    "connect",
    "feedback",
    "about us",
    "office",
    "address",
    "phone",
    "email",
]


# ============================================================================
# Исключения
# ============================================================================


class SiteParserError(Exception):
    """Базовая ошибка парсера сайта."""

    pass


class SiteNotAccessibleError(SiteParserError):
    """Сайт недоступен."""

    pass


class RateLimitExceededError(SiteParserError):
    """Превышен лимит запросов."""

    pass


# ============================================================================
# Парсер сайта
# ============================================================================


class SiteContactParser:
    """Парсинг контактов с сайта работодателя."""

    def __init__(self, config: SiteParserConfig | None = None):
        """
        Инициализировать парсер.

        Args:
            config: Конфигурация парсера
        """
        self.config = config or DEFAULT_CONFIG
        self._browser = None
        self._playwright = None
        self._page = None  # Переиспользуемая вкладка
        self._logged_contacts: set[tuple[str, str]] = (
            set()
        )  # (contact_type, normalized_value)

        # Инициализация requests сессии (используется всегда для первичной проверки)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        self.session.max_redirects = self.config.max_redirects

    def _init_browser(self):
        """Инициализировать браузер Playwright и создать вкладку."""
        if self._browser is not None and self._page is not None:
            return

        try:
            from playwright.sync_api import sync_playwright

            # Запускаем браузер если ещё не запущен
            if self._browser is None:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(
                    headless=self.config.headless
                )

            # Создаём вкладку если ещё не создана
            if self._page is None:
                self._page = self._browser.new_page()
                self._page.set_default_timeout(self.config.browser_timeout)

        except ImportError:
            logger.error(
                "Playwright не установлен. Установите: pip install playwright && playwright install"
            )
            raise
        except Exception as e:
            logger.error(f"Ошибка запуска браузера: {type(e).__name__}: {e}")
            raise

    def _close_browser(self):
        """Закрыть браузер Playwright."""
        # Закрываем вкладку
        if self._page:
            try:
                self._page.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии вкладки: {e}")
            finally:
                self._page = None

        # Закрываем браузер
        if self._browser:
            try:
                self._browser.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии браузера: {e}")
            finally:
                self._browser = None

        # Останавливаем Playwright
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                logger.warning(f"Ошибка при остановке Playwright: {e}")
            finally:
                self._playwright = None

    def parse_site(
        self, employer_id: int, employer_name: str, site_url: str
    ) -> Iterator[ContactModel]:
        """
        Парсить сайт работодателя на наличие контактов.

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя
            site_url: URL сайта работодателя

        Yields:
            Найденные контакты
        """
        # Нормализуем URL
        site_url = self._normalize_url(site_url)

        # Получаем главную страницу
        try:
            main_page_content = self._fetch_page(site_url)
            if main_page_content:
                # Извлекаем контакты с главной страницы
                yield from self._extract_contacts_from_page(
                    employer_id=employer_id,
                    employer_name=employer_name,
                    content=main_page_content,
                    url=site_url,
                )

                # Ищем страницы контактов
                yield from self._find_contact_pages(
                    employer_id=employer_id,
                    employer_name=employer_name,
                    base_url=site_url,
                    main_content=main_page_content,
                )
            else:
                logger.warning(f"Не удалось получить главную страницу: {site_url}")
        except SiteNotAccessibleError as e:
            logger.warning(f"Сайт недоступен {site_url}: {e}")
        except Exception as e:
            logger.error(f"Ошибка парсинга сайта {site_url}: {type(e).__name__}: {e}")

    def _normalize_url(self, url: str) -> str:
        """
        Нормализовать URL сайта.

        Args:
            url: Исходный URL

        Returns:
            Нормализованный URL
        """
        url = url.strip()

        # Добавляем схему если нет
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Убираем trailing slash
        url = url.rstrip("/")

        return url

    def _fetch_page(self, url: str) -> str | None:
        """
        Получить содержимое страницы.

        Если use_browser=True, использует Playwright для рендеринга JavaScript.
        Иначе использует requests для быстрых HTTP-запросов.

        Args:
            url: URL страницы

        Returns:
            Содержимое страницы или None
        """
        if self.config.use_browser:
            return self._fetch_page_browser(url)
        else:
            return self._fetch_page_requests(url)

    def _fetch_page_requests(self, url: str) -> str | None:
        """
        Получить содержимое страницы через requests.

        Args:
            url: URL страницы

        Returns:
            Содержимое страницы или None
        """
        try:
            logger.debug(f"GET {url}")
            response = self.session.get(
                url,
                timeout=(self.config.connect_timeout, self.config.timeout),
                allow_redirects=True,
            )
            logger.debug(f"GET {url} -> {response.status_code} ({len(response.text)})")

            if response.status_code == 200:
                return response.text
            elif response.status_code == 404:
                return None
            elif response.status_code == 429:
                logger.warning(f"Rate limit exceeded: {url}")
                raise RateLimitExceededError(f"Rate limit exceeded for {url}")
            else:
                return None

        except RequestException as e:
            logger.debug(f"Ошибка запроса {url}: {type(e).__name__}: {e}")
            return None

    def _fetch_page_browser(self, url: str) -> str | None:
        """
        Получить содержимое страницы через Playwright.

        Использует переиспользуемую вкладку для всех запросов.

        Args:
            url: URL страницы

        Returns:
            Содержимое страницы или None
        """
        self._init_browser()

        try:
            response = self._page.goto(url)

            if response and response.status == 200:
                # Ждём загрузки контента (с таймаутом)
                try:
                    self._page.wait_for_load_state(
                        "networkidle", timeout=30000
                    )  # 30 сек на networkidle
                except Exception as e:
                    logger.warning(
                        f"Таймаут networkidle для {url}: {e}, продолжаем с domcontentloaded"
                    )
                    self._page.wait_for_load_state("domcontentloaded")

                content = self._page.content()
                logger.debug(f"GET {url} -> 200 ({len(content)})")
                return content
            elif response and response.status == 404:
                return None
            else:
                status = response.status if response else "unknown"
                logger.debug(f"GET {url} -> {status}")
                return None

        except Exception as e:
            logger.error(f"Ошибка браузера для {url}: {type(e).__name__}: {e}")
            return None

    def _extract_contacts_from_page(
        self, employer_id: int, employer_name: str, content: str, url: str
    ) -> Iterator[ContactModel]:
        """
        Извлечь контакты из содержимого страницы.

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя
            content: HTML-содержимое страницы
            url: URL страницы

        Yields:
            Найденные контакты
        """
        # Извлекаем email
        for email in extract_emails(content):
            normalized = normalize_email(email)
            contact_key = ("email", normalized)
            if contact_key not in self._logged_contacts:
                self._logged_contacts.add(contact_key)
                logger.debug(f"Email: {email}")
            yield ContactModel(
                employer_id=employer_id,
                employer_name=employer_name,
                contact_type="email",
                value=email,
                source="site",
                source_url=url,
                normalized_value=normalized,
            )

        # Извлекаем телефоны
        for phone in extract_phones(content):
            normalized = normalize_phone(phone)
            contact_key = ("phone", normalized)
            if contact_key not in self._logged_contacts:
                self._logged_contacts.add(contact_key)
                logger.debug(f"Phone: {phone}")
            yield ContactModel(
                employer_id=employer_id,
                employer_name=employer_name,
                contact_type="phone",
                value=phone,
                source="site",
                source_url=url,
                normalized_value=normalized,
            )

    def _find_contact_pages(
        self, employer_id: int, employer_name: str, base_url: str, main_content: str
    ) -> Iterator[ContactModel]:
        """
        Найти и парсить страницы контактов.

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя
            base_url: Базовый URL сайта
            main_content: Содержимое главной страницы

        Yields:
            Найденные контакты
        """
        pages_visited = 0
        urls_to_try = set()

        # 1. Пробуем типовые URL
        for pattern in CONTACT_URL_PATTERNS:
            contact_url = base_url + pattern
            urls_to_try.add(contact_url)

        # 2. Ищем ссылки по ключевым словам в навигации
        found_links = self._find_contact_links(base_url, main_content)
        urls_to_try.update(found_links)

        # Парсим найденные страницы
        for contact_url in urls_to_try:
            if pages_visited >= self.config.max_pages_per_site:
                break

            # Задержка между запросами
            if pages_visited > 0:
                time.sleep(self.config.delay_between_requests)

            content = self._fetch_page(contact_url)
            if content:
                pages_visited += 1
                yield from self._extract_contacts_from_page(
                    employer_id=employer_id,
                    employer_name=employer_name,
                    content=content,
                    url=contact_url,
                )

    def _find_contact_links(self, base_url: str, content: str) -> set[str]:
        """
        Найти ссылки на страницы контактов по ключевым словам.

        Args:
            base_url: Базовый URL сайта
            content: HTML-содержимое страницы

        Returns:
            Множество найденных URL
        """
        found_urls = set()
        base_domain = urlparse(base_url).netloc

        # Ищем все ссылки
        href_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
        all_links = href_pattern.finditer(content)

        for match in all_links:
            href = match.group(1)

            # Пропускаем якоря, javascript, mailto, tel
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            # Нормализуем URL
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # Проверяем, что это тот же домен
            if parsed.netloc != base_domain:
                continue

            # Проверяем по ключевым словам
            href_lower = href.lower()
            text_around = content[
                max(0, match.start() - 100) : match.end() + 100
            ].lower()

            keywords = CONTACT_KEYWORDS_RU + CONTACT_KEYWORDS_EN
            for keyword in keywords:
                if keyword in href_lower or keyword in text_around:
                    found_urls.add(full_url.split("#")[0].rstrip("/"))
                    break

        return found_urls

    def close(self):
        """Закрыть сессию и браузер."""
        try:
            self.session.close()
        except Exception as e:
            logger.warning(f"Ошибка при закрытии сессии: {e}")
        self._close_browser()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
