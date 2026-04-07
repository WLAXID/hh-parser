from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, List, Set

from ..api.client import ApiClient
from ..storage.models.employer import EmployerModel

if TYPE_CHECKING:
    from ..main import HHParserTool

logger = logging.getLogger(__name__)


class Operation:
    """Парсинг работодателей с hh.ru"""

    def run(self, tool: "HHParserTool", args, progress_callback=None) -> int | None:
        logger.info("Начало парсинга работодателей")
        api_client: ApiClient = tool.api_client
        storage = tool.storage

        if args.mode == "stats-only":
            return self._update_stats_only(storage, api_client)

        employer_ids: Set[int] = set()

        # Получаем дерево регионов
        logger.info("Получение справочника регионов...")
        areas = self._get_areas(api_client)
        logger.info(f"Найдено {len(areas)} регионов (включая подрегионы)")

        # Для каждого региона выполняем поиск работодателей
        for area in areas:
            area_id = str(area["id"])
            area_name = area.get("name", "")
            logger.info(f"Обработка региона: {area_name} (ID: {area_id})")

            # Проверяем, нужно ли фильтровать по industry и другим параметрам
            params = {}

            if args.area:
                # Если указаны конкретные регионы, то используем только их
                if area_id not in args.area:
                    continue
                # Если мы дошли сюда, то регион подходит, добавляем его в параметры
                params["area"] = area_id
            if args.only_with_vacancies:
                params["only_with_vacancies"] = True
            params["sort_by"] = args.sort_by
            params["per_page"] = args.per_page

            # Выполняем поиск работодателей по региону с пагинацией
            page = 0
            processed_in_region = 0
            while True:
                params["page"] = page
                logger.debug(
                    f"Запрос работодателей: area={area_id}, page={page}, params={params}"
                )
                try:
                    response = api_client.get("/employers", params=params)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Ошибка при запросе работодателей: {e}")
                    # В случае ошибки делаем паузу и пробуем снова?
                    time.sleep(5)
                    continue

                # response ожидается как словарь с ключом 'items' и пагинацией
                items = response.get("items", [])
                pages = response.get("pages", 0)
                found = response.get("found", 0)
                if page == 0:
                    logger.info(f"Найдено работодателей в регионе {area_name}: {found}")
                    if pages > 1:
                        logger.info(f"Страниц для обработки: {pages}")
                    # Проверка лимита 5000 результатов согласно PLAN.md
                    # API hh.ru не возвращает результаты глубже 5000
                    if found >= 5000:
                        logger.warning(
                            f"\nРегион {area_name} содержит >= 5000 работодателей ({found}). "
                            f"Рекомендуется обрабатывать подрегионы для полного охвата.\n"
                        )

                if not items:
                    logger.debug(f"На странице {page} нет данных, завершаем пагинацию")
                    break

                # Обрабатываем каждого работодателя на странице
                for emp_short in items:
                    emp_id = emp_short.get("id")
                    if emp_id is None:
                        continue
                    emp_id_int = int(emp_id)
                    # Если режим resume и работодатель уже есть в БД, пропускаем
                    if args.resume:
                        existing = storage.employers.get(emp_id_int)
                        if existing is not None:
                            logger.debug(
                                f"Работодатель {emp_id_int} уже существует в БД, пропускаем"
                            )
                            continue
                    if emp_id_int in employer_ids:
                        continue

                    # Получаем полную информацию о работодателе
                    try:
                        emp_details = api_client.get(f"/employers/{emp_id}")
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        logger.error(
                            f"Ошибка при получении деталей работодателя {emp_id}: {e}"
                        )
                        # Пропускаем этого работодателя, но продолжаем
                        continue

                    # Извлекаем нужные поля
                    name = emp_details.get("name")
                    site_url = emp_details.get("site_url")
                    # Нормализуем site_url
                    site_url = emp_details.get("site_url")
                    if site_url:
                        site_url = site_url.strip()
                        if not site_url or site_url in ("http://", "https://"):
                            site_url = None
                    else:
                        site_url = None
                    alternate_url = emp_details.get("alternate_url")
                    open_vacancies = emp_details.get("open_vacancies", 0)

                    # Отрасли и регион могут быть в деталях
                    # industries - это список объектов [{id, name}], сохраняем как JSON
                    industries_raw = emp_details.get("industries")
                    # area - это объект {id, name}, извлекаем name
                    area_obj = emp_details.get("area")
                    area_name_from_details = area_obj.get("name") if area_obj else None

                    # Если режим full, то также получаем вакансии для расчёта avg_responses
                    total_responses = 0
                    avg_responses = 0.0
                    if args.mode == "full":
                        total_responses, avg_responses = self._get_vacancies_stats(
                            api_client, emp_id_int
                        )

                    # Сохраняем в базу данных
                    # Преобразуем industries в JSON-строку
                    import json as json_module

                    industries_json = (
                        json_module.dumps(industries_raw, ensure_ascii=False)
                        if industries_raw is not None
                        else None
                    )
                    employer = EmployerModel(
                        id=emp_id_int,
                        name=name or "",
                        site_url=site_url,
                        alternate_url=alternate_url,
                        open_vacancies=open_vacancies,
                        total_responses=total_responses,
                        avg_responses=avg_responses,
                        industries=industries_json,
                        area_name=area_name_from_details,
                    )
                    try:
                        storage.employers.save(employer)
                        employer_ids.add(emp_id_int)
                        processed_in_region += 1

                        if progress_callback:
                            progress_callback(
                                employer_name=name,
                                employer_id=emp_id_int,
                                region=area_name,
                                has_site=site_url is not None,
                                total_found=found,
                                site_url=site_url,
                                open_vacancies=open_vacancies,
                                alternate_url=alternate_url,
                                avg_responses=avg_responses
                                if args.mode == "full"
                                else None,
                            )
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        logger.error(
                            f"Ошибка при сохранении работодателя {emp_id} в БД: {e}"
                        )

                    # Выводим информацию о сохранённом работодателе
                    log_parts = [f"[{name}]"]
                    log_parts.append(f"вакансий: {open_vacancies}")
                    if args.mode == "full":
                        log_parts.append(f"ср. откликов: {avg_responses:.1f}")
                    if site_url:
                        log_parts.append(f"сайт: {site_url}")
                    if alternate_url:
                        log_parts.append(f"hh: {alternate_url}")
                    logger.info(" | ".join(log_parts))

                    # Проверяем лимит количества работодателей
                    if (
                        hasattr(args, "limit")
                        and args.limit > 0
                        and len(employer_ids) >= args.limit
                    ):
                        logger.info(f"Достигнут лимит работодателей: {args.limit}")
                        break

                page += 1
                if page >= pages:
                    break

                # Проверяем лимит перед следующей страницей
                if (
                    hasattr(args, "limit")
                    and args.limit > 0
                    and len(employer_ids) >= args.limit
                ):
                    break

                # Небольшая пауза между страницами (уже есть в API client, но добавим свою)
                time.sleep(0.5)

            logger.info(
                f"Завершена обработка региона {area_name}. Уникальных работодателей всего: {len(employer_ids)}"
            )

        logger.info(
            f"Парсинг завержен. Всего уникальных работодателей: {len(employer_ids)}"
        )
        return 0

    def _get_areas(self, api_client: ApiClient) -> List[dict]:
        """Получает дерево регионов и возвращает плоский список всех регионов (включая подрегионы)."""
        try:
            response = api_client.get("/areas")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.error(f"Ошибка при получении справочника регионов: {e}")
            return []

        # response ожидается как список стран, каждая страна содержит регионы и т.д.
        def flatten_areas(areas_list: List[dict]) -> List[dict]:
            flat = []
            for area in areas_list:
                flat.append(area)
                if "areas" in area and isinstance(area["areas"], list):
                    flat.extend(flatten_areas(area["areas"]))
            return flat

        return flatten_areas(response)

    def _get_vacancies_stats(
        self, api_client: ApiClient, employer_id: int
    ) -> tuple[int, float]:
        """Получает статистику по вакансиям работодателя для расчёта avg_responses."""
        total_responses = 0
        total_vacancies = 0  # Общее количество вакансий (не только с откликами)
        page = 0
        while True:
            params = {
                "page": page,
                "per_page": 100,
                "responses_count_enabled": True,  # Включить счётчик откликов
                "employer_id": employer_id,  # Фильтр по работодателю
            }
            try:
                response = api_client.get("/vacancies", params=params)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(
                    f"Ошибка при получении вакансий для работодателя {employer_id}: {e}"
                )
                # В случае ошибки делаем паузу и пробуем снова?
                time.sleep(5)
                continue

            items = response.get("items", [])
            pages = response.get("pages", 0)
            if not items:
                break

            for vac in items:
                # Согласно API, счётчики откликов находятся в поле counters
                counters = vac.get("counters", {})
                responses = counters.get("responses", 0)
                total_responses += responses
                total_vacancies += 1  # Считаем все вакансии

            page += 1
            if page >= pages:
                break
            # Пауза между страницами запросов вакансий
            time.sleep(0.5)

        # avg_responses = сумма откликов / количество вакансий
        avg_responses = (
            total_responses / total_vacancies if total_vacancies > 0 else 0.0
        )
        return total_responses, avg_responses

    def _update_stats_only(self, storage, api_client: ApiClient) -> int | None:
        """Обновляет статистику (avg_responses) для существующих работодателей в БД."""
        logger.info("Начало обновления статистики для существующих работодателей")
        # Получаем всех работодателей из БД
        employers = list(storage.employers.find())
        logger.info(
            f"Найдено {len(employers)} работодателей в БД для обновления статистики"
        )

        for i, employer in enumerate(employers, 1):
            logger.info(
                f"Обработка работодателя {i}/{len(employers)}: {employer.name} (ID: {employer.id})"
            )
            try:
                total_responses, avg_responses = self._get_vacancies_stats(
                    api_client, employer.id
                )
                # Обновляем работодателя в БД
                employer.total_responses = total_responses
                employer.avg_responses = avg_responses
                storage.employers.save(employer)
                logger.debug(
                    f"Обновлён работодатель {employer.id}: total_responses={total_responses}, avg_responses={avg_responses}"
                )
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(
                    f"Ошибка при обновлении статистики для работодателя {employer.id}: {e}"
                )
            # Пауза между запросами, чтобы не превысить лимиты API
            time.sleep(0.5)

        logger.info("Обновление статистики завершено")
        return 0


if __name__ == "__main__":
    # Для тестирования можно запустить напрямую
    pass
