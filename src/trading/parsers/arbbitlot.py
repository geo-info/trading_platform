"""АРБбитЛот — банкротные торги, движок iTender (ASP.NET WebForms).

Обход в два уровня: листинг даёт строку таблицы и ссылку на лот, страница лота
— подробности. Айтем отдаётся один на лот, уже со сведениями обеих страниц.

Сертификат площадки просрочен на их стороне, CA-бандл тут не помогает,
поэтому проверка TLS отключена. Это снимает и защиту от подмены трафика —
цена за доступ к сайту, который иначе не открыть вовсе.

Пагинация: ссылки пейджера — не href, а ``__doPostBack``, и страница N+1
берётся POST-ом, который несёт токены страницы N. Цепочку нельзя
распараллелить и нельзя начать с середины — ``concurrency`` обязан остаться
единицей.

Ходим **обычными postback-ами**, без заголовка ``X-MicrosoftAjax``. Тогда
сервер отвечает целой HTML-страницей, а не дельтой UpdatePanel (``text/plain``
с записями ``длина|тип|имя|значение|``), и скрытые поля на каждом шаге лежат
там же, где на первом, — в тегах ``input``. Одна форма ответа на весь обход,
одна функция для токенов, никаких развилок по номеру страницы.

    uv run python -m trading.parsers.arbbitlot
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collector import Parser, Response, Settings, open_crawler
from parsel import Selector

from trading.storage import TinyDbStore

SOURCE = "arbbitlot"
MAX_PAGES = 21

#: Корень репозитория: src/trading/parsers/arbbitlot.py -> вверх на четыре уровня.
DB_PATH = Path(__file__).resolve().parents[3] / "data" / f"{SOURCE}.json"


def clean(value: str | None) -> str | None:
    """Схлопнуть пробелы и неразрывные пробелы; пустая строка — это ``None``."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip() or None


def cell(node: Selector) -> str | None:
    return clean(" ".join(node.xpath(".//text()[not(ancestor::a)]").getall()))


def extract_initial_tokens(page: Selector) -> tuple[str | None, str | None]:
    """Extract tokens from the initial HTML page (hidden form fields)."""
    cviewstate = page.xpath('//input[@id="__CVIEWSTATE"]/@value').get()
    eventvalidation = page.xpath('//input[@id="__EVENTVALIDATION"]/@value').get()
    return cviewstate, eventvalidation


def find_next_target(page: Selector, num_page: int) -> str | None:
    next_num, block = f'normalize-space()="{num_page + 1}"', 'normalize-space()=">>"'
    href = page.xpath(f'(//td[@class="pager"])[1]//a[{next_num} or {block}]/@href').get()
    match = re.search(r"__doPostBack\('([^']+)'", href or "")
    return match.group(1) if match else None


def build_payload(target: str, cviewstate: str, eventvalidation: str) -> dict[str, str]:
    """Тело POST, повторяющее клик по ссылке пейджера."""
    return {
        "__EVENTTARGET": target,
        "__EVENTARGUMENT": "",
        "__CVIEWSTATE": cviewstate,
        "__EVENTVALIDATION": eventvalidation,
    }


def parse_rows(page: Selector) -> list[dict[str, Any]]:
    """Строки таблицы листинга.

    Порядок колонок задан вёрсткой и от площадки к площадке разный, поэтому
    разбор идёт по номерам ячеек, а не по заголовкам: заголовок — это текст
    для человека, его переформулируют, не трогая разметку.
    """
    rows = []
    for tr in page.xpath('//tr[@class="gridRow"]'):
        cells = tr.xpath("./td")
        if len(cells) < 11:
            continue
        lot_url = tr.xpath(".//a[contains(@href,'/lots/view/')]/@href").get()
        rows.append(
            {
                "lot_url": clean(lot_url),
                "trade_id": clean(cells[0].xpath("string(.)").get()),
                "auction_name": clean(cells[1].xpath("string(.)").get()),
                "lot_num": clean(cells[2].xpath("string(.)").get()),
                "description": clean(cells[3].xpath("string(.)").get()),
                "price": clean(cells[4].xpath("string(.)").get()),
                "organizer": clean(cells[5].xpath("string(.)").get()),
                "bids_end": clean(cells[6].xpath("string(.)").get()),
                "auction_date": clean(cells[7].xpath("string(.)").get()),
                "status": clean(cells[8].xpath("string(.)").get()),
                "winner": clean(cells[9].xpath("string(.)").get()),
                "trade_type": clean(cells[10].xpath("string(.)").get()),
            }
        )
    return rows


def parse_detail(page: Selector) -> dict[str, dict[str, str | None]]:
    """Разделы страницы лота: легенда -> пары «подпись: значение».

    Страница собрана из ``<fieldset><legend>…</legend>`` с таблицами внутри,
    где подписи лежат в ``td.tdTitle``, а значения — в следующих ``td.tdContent``.
    Это устойчивее, чем брать таблицы по порядку: вокруг ещё полтора десятка
    таблиц меню и форма входа.

    Разделы без единого значения отбрасываются — так со страницы уходит форма
    загрузки документа, у которой есть подписи, но нечего показать.
    """
    sections: dict[str, dict[str, str | None]] = {}
    for fieldset in page.xpath("//fieldset[legend]"):
        legend = clean(fieldset.xpath("./legend/text()").get())
        if not legend:
            continue

        pairs: dict[str, str | None] = {}
        titles = fieldset.xpath(".//td[@class='tdTitle']")
        values = fieldset.xpath(".//td[@class='tdContent']")
        for title, value in zip(titles, values, strict=False):
            label = (cell(title) or "").rstrip(":")
            if label:
                pairs[label] = cell(value)

        if any(pairs.values()):
            sections[re.compile(r"\s*№\s*\S+\s*$").sub("", legend)] = pairs

    return sections


class Arbbitlot(Parser):
    name = SOURCE
    start_urls = ["https://torgi.arbbitlot.ru/public/purchases-all/"]
    settings = Settings(delay=0.5, skip_tls_verify=True)

    async def parse(self, response: Response) -> Any:
        """Листинг: раздать запросы на страницы лотов и шагнуть на следующую."""
        page = response.selector()
        num_page = response.metadata.get("page", 1)
        rows = parse_rows(page)
        await self.log(f"{response.status} | страница {num_page} | лотов {len(rows)}")

        for row in rows:
            if row["lot_url"]:
                yield response.follow(row["lot_url"], callback=self.parse_lot, metadata={"row": row})

        if num_page >= MAX_PAGES:
            await self.log(f"остановка: предел MAX_PAGES={MAX_PAGES}")
            return

        next_target = find_next_target(page, num_page)
        if next_target is None:
            await self.log(f"страница {num_page} последняя")
            return

        cviewstate, eventvalidation = extract_initial_tokens(page)
        if not cviewstate or not eventvalidation:
            # Молча выйти здесь — значит выдать обрыв цепочки за её конец.
            await self.log(f"страница {num_page}: токенов нет, дальше идти нечем")
            return

        yield self.request(
            response.request.url,
            method="POST",
            data=build_payload(next_target, cviewstate, eventvalidation),
            metadata={"page": num_page + 1},
        )

    async def parse_lot(self, response: Response) -> Any:
        """Страница лота: слить строку листинга с подробностями в один айтем."""
        url = response.request.url
        match = re.compile(r"/lots/view/(\d+)").search(url)
        if match is None:
            # Без идентификатора документ нечем ключевать в хранилище.
            await self.log(f"пропуск: в ссылке нет номера лота — {url}")
            return

        item = {
            "source": SOURCE,
            "lot_id": match.group(1),
            "url": url,
            **response.metadata["row"],
            "detail": parse_detail(response.selector()),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        yield item


async def crawl(store: TinyDbStore) -> tuple[Any, int, int]:
    """Обойти площадку, складывая лоты в хранилище по мере поступления.

    Поток, а не ``collect()``: айтемы пишутся сразу, и обход, прерванный на
    середине, оставляет после себя всё, что успел собрать.
    """
    new = updated = 0
    async with open_crawler(Arbbitlot) as crawler:
        async for item in crawler.stream():
            if store.upsert(item):
                new += 1
            else:
                updated += 1
    return crawler.stats, new, updated


def main() -> None:
    # Логи парсера и фреймворка идут через stdlib logging уровнем INFO, а у root
    # по умолчанию нет обработчиков и порог WARNING — без basicConfig всё INFO
    # молча отбрасывается. Консоль Windows вдобавок не UTF-8, а в логах кириллица.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with TinyDbStore(DB_PATH) as store:
        stats, new, updated = asyncio.run(crawl(store))
        total = store.count()

    print(f"лотов получено {stats.items}: новых {new}, обновлено {updated}")
    print(f"запросов {stats.requests}, ошибок {stats.errors}, причина остановки {stats.reason}")
    print(f"в хранилище {total} документов -> {DB_PATH}")


if __name__ == "__main__":
    main()
