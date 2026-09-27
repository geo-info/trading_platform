"""Общее для площадок всех движков: настройки HTTP, параметры прогона, айтем лота.

Движки разные — iTender, Kendo, btorg, rus-on, — а договорённости с
площадками одни: запросы по одному и с паузой, терпимость к сбоям, предел
страниц и окно по дате. Держать их у одного движка значило бы, что остальные
либо импортируют чужое, либо копируют и расходятся.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urljoin

from collector import Response, Settings
from pydantic import ValidationError

from core.lot import Lot
from core.parsing import parse_datetime
from core.settings import settings as config

#: Настройки HTTP, общие для всех площадок. Площадка со своей
#: особенностью сужает их через ``narrow`` — см. arbbitlot и meta_invest.
#:
#: concurrency остаётся единицей, и это измерено, а не осторожность: площадка
#: обрабатывает наши запросы по одному, поэтому латентность растёт ровно
#: пропорционально числу воркеров, а запросов в секунду не прибавляется.
#:
#: max_errors — сколько упавших запросов площадка переживает. Фреймворк по
#: умолчанию останавливает обход на первом, и одна битая страница лота роняла
#: бы площадку на тысяче лотов. Разбор лота сам почти не падает (невалидный
#: лот пишется запасным документом), так что ошибка здесь — это сеть после
#: ретраев или вёрстка, сломанная для всех страниц. 50 — около 2,5% от
#: 2000 запросов обхода в 100 страниц: случайные сбои проходят, а сломанная
#: вёрстка останавливает площадку через 50 впустую потраченных запросов, а не
#: через две тысячи. На один прогон — ``--max-errors``.
BASE_SETTINGS = Settings(concurrency=1, delay=config.delay, timeout=config.http_timeout, max_errors=50)


def narrow(**overrides: Any) -> Settings:
    """Настройки площадки: общие плюс её особенность.

    Через ``replace``, а не конструктором, чтобы площадка со своей причудой
    не теряла общие ``delay`` и ``timeout``, когда те поменяются.
    """
    return replace(BASE_SETTINGS, **overrides)


@dataclass(frozen=True)
class CrawlParams:
    """Что задаётся на один прогон: предел страниц и окно по дате.

    Раньше это были атрибуты класса, и run_all переписывал их у класса на весь
    процесс: два обхода в одном процессе видели значения друг друга. Теперь
    фреймворк собирает свой экземпляр на каждый прогон, приводит строки из
    командной строки к типам и отказывает в незнакомом ключе до первого
    запроса — окно, молча не применённое из-за опечатки, обошло бы всё.

    Умолчания — из ``core.settings``, то есть из окружения.
    """

    #: Предохранитель обхода. Без потолка ошибка в пагинации крутится вечно.
    max_pages: int = config.max_pages
    #: Окно по дате, см. ``Settings.since`` и ``older_than``.
    since: date | None = config.since


def older_than(deadlines: list[str | None], since: date) -> bool:
    """Все сроки страницы раньше ``since`` — дальше листать незачем.

    Листинги отсортированы по номеру торгов, то есть по публикации, а даты
    публикации в них нет. Ближайшая замена — срок приёма заявок: он растёт
    вместе с номером, хоть и не строго (у публичного предложения интервалы
    тянутся месяцами). Поэтому останавливаемся не на первой старой строке, а
    когда старая вся страница. Строки без даты решения не принимают.
    """
    parsed = [d.date() for value in deadlines if (d := parse_datetime(value))]
    return bool(parsed) and max(parsed) < since


def rejected(
    source: str, lot_id: str, url: str, fetched_at: str, row: dict[str, Any], exc: Exception
) -> dict[str, Any]:
    """Запасной документ лота, которого модель не пропустила.

    Без него исключение ушло бы во фреймворк, тот посчитал бы ошибку, и лот не
    попал бы в базу вовсе — из-за одного поля. Документ несёт ключ, сырые
    поля разбора и текст ошибки в ``validation``, чтобы разбирать было из чего.
    """
    return {
        "source": source,
        "lot_id": lot_id,
        "url": url,
        "fetched_at": fetched_at,
        "row": row,
        "validation": {"ok": False, "errors": [f"модель: {exc}"], "unknown_labels": []},
    }


async def paging_stops(crawler: Any, num_page: int, deadlines: list[str | None] | None) -> bool:
    """Пора ли прекращать листать листинг: предел страниц или окно по дате.

    ``deadlines`` — сроки приёма заявок строк страницы; ``None`` — в листинге
    движка срока нет, и окно на нём не действует. Причину остановки пишет в лог.
    """
    if num_page >= crawler.params.max_pages:
        await crawler.log(f"остановка: предел max_pages={crawler.params.max_pages}")
        return True
    since = crawler.params.since
    if since is not None and deadlines is not None and older_than(deadlines, since):
        await crawler.log(f"остановка: вся страница {num_page} закрыла приём заявок до {since}")
        return True
    return False


def check_status(response: Response) -> None:
    """Не-200 — ошибка запроса, а не пустая страница.

    Страница ошибки разбирается в ноль торгов, и площадка, чей листинг
    переехал, выглядела бы в итоговой таблице обходом без лотов. Исключение
    фреймворк засчитывает в ошибки, и площадка видна в колонке «ош».
    Повторяемые статусы (429, 5xx) фреймворк сначала повторяет сам.
    """
    if response.status != 200:
        raise ValueError(f"{response.status} для {response.request.url}")


def lot_item(source: str, page_url: str, lot: dict[str, Any]) -> dict[str, Any]:
    """Айтем лота через модель ``core.lot.Lot``; не пропущенный моделью — запасным документом.

    У лота своя страница есть не на всех движках — тогда адрес лота это адрес
    страницы, с которой он разобран.
    """
    fetched_at = datetime.now(UTC).isoformat()
    url = urljoin(page_url, lot["lot_url"]) if lot.get("lot_url") else page_url
    try:
        return Lot.model_validate(
            {**lot, "source": source, "url": url, "fetched_at": fetched_at}
        ).model_dump()
    except ValidationError as exc:
        return rejected(source, str(lot["lot_id"]), url, fetched_at, lot, exc)
