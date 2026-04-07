"""
Модуль парсинга контактов с сайта работодателя.

Стратегия поиска:
1. Получаем главную страницу сайта
2. Извлекаем все ссылки <a href> и их anchor text
3. Ищем ключевые слова в anchor text ссылок
4. Переходим только по найденным ссылкам
5. Типовые URL паттерны используем только как fallback
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, Iterator
from urllib.parse import urljoin, urlparse

import requests
from requests.exceptions import RequestException

from hh_parser.cli.config import DEFAULT_SITE_CONFIG, SiteParserConfig
from hh_parser.storage.models.contact import ContactModel

from ..exceptions import RateLimitExceededError, SiteNotAccessibleError
from ..extractors import (
    extract_emails,
    extract_phones,
    normalize_email,
    normalize_phone,
)
from ..keywords import CONTACT_KEYWORDS

logger = logging.getLogger(__name__)


class SiteContactParser:
    """Парсинг контактов с сайта работодателя."""

    def __init__(
        self,
        config: SiteParserConfig | None = None,
        on_url_change: Callable[[str], None] | None = None,
    ):
        """
        Инициализировать парсер.

        Args:
            config: Конфигурация парсера
            on_url_change: Callback-функция, вызываемая при переходе на новый URL
        """
        self.config = config or DEFAULT_SITE_CONFIG
        self.on_url_change = on_url_change
        self._logged_contacts: set[tuple[str, str]] = (
            set()
        )  # (contact_type, normalized_value)

        # Инициализация requests сессии
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        self.session.max_redirects = self.config.max_redirects

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
                raise SiteNotAccessibleError(
                    f"Не удалось получить главную страницу: {site_url}"
                )
        except KeyboardInterrupt:
            raise
        except SiteNotAccessibleError:
            raise
        except Exception as e:
            raise SiteNotAccessibleError(
                f"Ошибка парсинга сайта: {type(e).__name__}: {e}"
            ) from e

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
        Получить содержимое страницы через requests.

        Args:
            url: URL страницы

        Returns:
            Содержимое страницы или None
        """
        # Вызываем callback перед запросом
        if self.on_url_change:
            self.on_url_change(url)

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

        except KeyboardInterrupt:
            raise
        except RequestException as e:
            logger.debug(f"Ошибка запроса {url}: {type(e).__name__}: {e}")
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
        self,
        employer_id: int,
        employer_name: str,
        base_url: str,
        main_content: str,
    ) -> Iterator[ContactModel]:
        """
        Найти и парсить страницы контактов.

        Сначала ищем ссылки на главной странице по ключевым словам в anchor text.
        Если не нашли — используем типовые URL паттерны как fallback.

        Args:
            employer_id: ID работодателя
            employer_name: Название работодателя
            base_url: Базовый URL сайта
            main_content: Содержимое главной страницы

        Yields:
            Найденные контакты
        """
        pages_visited = 0
        urls_to_try: list[str] = []
        seen_urls: set[str] = set()

        # 1. Ищем ссылки по ключевым словам в anchor text на главной странице
        found_links = self._find_contact_links(base_url, main_content)
        for url in found_links:
            if url not in seen_urls:
                seen_urls.add(url)
                urls_to_try.append(url)

        # 2. Если ссылки не найдены — не делаем fallback, просто пропускаем сайт
        if not urls_to_try:
            logger.debug("Ссылки по ключевым словам не найдены, пропускаем сайт")
            return
        else:
            logger.debug(f"Найдено {len(urls_to_try)} ссылок по ключевым словам")

        # Парсим найденные страницы
        for contact_url in urls_to_try:
            if pages_visited >= self.config.max_pages_per_site:
                break

            # Задержка между запросами
            if pages_visited > 0:
                try:
                    time.sleep(self.config.delay_between_requests)
                except KeyboardInterrupt:
                    logger.info("Парсинг прерван пользователем во время задержки")
                    raise

            try:
                content = self._fetch_page(contact_url)
                if content:
                    pages_visited += 1
                    yield from self._extract_contacts_from_page(
                        employer_id=employer_id,
                        employer_name=employer_name,
                        content=content,
                        url=contact_url,
                    )
            except KeyboardInterrupt:
                logger.info("Парсинг прерван пользователем")
                raise

    def _find_contact_links(self, base_url: str, content: str) -> list[str]:
        """
        Найти ссылки на страницы контактов по ключевым словам в anchor text.

        Ищем все <a> теги, извлекаем текст ссылки (anchor text)
        и проверяем наличие ключевых слов.

        Args:
            base_url: Базовый URL сайта
            content: HTML-содержимое страницы

        Returns:
            Список найденных URL (без дубликатов)
        """
        found_urls: list[str] = []
        seen_urls: set[str] = set()
        base_domain = urlparse(base_url).netloc

        # Паттерн для поиска <a> тегов с href и текстом ссылки
        # Совпадает: <a ... href="..." ...>текст ссылки</a>
        link_pattern = re.compile(
            r'<a\s[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )

        for match in link_pattern.finditer(content):
            href = match.group(1)
            anchor_text = match.group(2)

            # Пропускаем якоря, javascript, mailto, tel
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            # Пропускаем пустые href
            if not href or href == "/":
                continue

            # Нормализуем URL
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # Проверяем, что это тот же домен
            if parsed.netloc and parsed.netloc != base_domain:
                continue

            # Убираем дубликаты
            normalized_url = full_url.split("#")[0].rstrip("/")
            if normalized_url in seen_urls:
                continue

            # Проверяем anchor text по ключевым словам
            # Очищаем anchor text от HTML тегов
            clean_anchor = re.sub(r"<[^>]+>", " ", anchor_text).strip().lower()

            # Также проверяем href на наличие ключевых слов
            href_lower = href.lower()

            matched = False
            for keyword in CONTACT_KEYWORDS:
                if keyword in clean_anchor or keyword in href_lower:
                    matched = True
                    break

            if matched:
                seen_urls.add(normalized_url)
                found_urls.append(normalized_url)
                logger.debug(
                    f"Найдена ссылка: {normalized_url} (anchor: {clean_anchor[:50]})"
                )

        return found_urls

    def close(self):
        """Закрыть сессию."""
        try:
            self.session.close()
        except Exception as e:
            logger.warning(f"Ошибка при закрытии сессии: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


__all__ = ("SiteContactParser",)
