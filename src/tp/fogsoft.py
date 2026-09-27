"""TenderFogsoft — обход площадок на движке iTender (Fogsoft).

Шестнадцать площадок на этом движке отличаются друг от друга доменом и парой
настроек — вёрстка у них одна. Поэтому обход живёт здесь, разметка — в
``tp.marking.fogsoft``, а модуль площадки — это её имя, адрес и то, чем она
особенная.

Обход в два уровня: листинг даёт строку таблицы и ссылку на лот, страница лота
— подробности. Айтем отдаётся один на лот, уже со сведениями обеих страниц.

Пагинация: ссылки пейджера — не href, а ``__doPostBack``, и страница N+1
берётся POST-ом, который несёт токены страницы N. Цепочку нельзя
распараллелить и нельзя начать с середины — ``concurrency`` обязан остаться
единицей.

Ходим **обычными postback-ами**, без заголовка ``X-MicrosoftAjax``. Тогда
сервер отвечает целой HTML-страницей, а не дельтой UpdatePanel (``text/plain``
с записями ``длина|тип|имя|значение|``), и форма на каждом шаге та же, что на
первом. Тело POST собирает ``Response.form_request()`` фреймворка — все поля
формы, как отправил бы браузер, с токенами ``__CVIEWSTATE`` и
``__EVENTVALIDATION`` в их числе; парсер называет только то, что меняет.

Новая площадка — модуль в ``tp.platforms.fogsoft``::

    class Centerr(TenderFogsoft):
        name = "centerr"
        DOMAIN = "https://bankrupt.centerr.ru"
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, ClassVar

from collector import Crawler, Response
from parsel import Selector
from pydantic import ValidationError

from core.lot import Lot
from core.parsing import parse_price
from tp.common import BASE_SETTINGS, CrawlParams, paging_stops, rejected
from tp.marking.fogsoft import (
    LOT_SECTION,
    REQUIRED,
    filter_resets,
    find_next_target,
    has_viewstate,
    parse_attachments,
    parse_price_schedule,
    parse_rows,
    raw_detail,
    search_button,
)
from tp.marking.fogsoft_known_labels import unknown_labels
from tp.marking.fogsoft_labels import canon_detail


class FogsoftLot(Lot):
    """Лот iTender: общие сверки плюс сверки листинга со страницей лота.

    Страница лота здесь — разделы с подписями, и у движка есть реестр
    известных подписей. У других движков страница устроена иначе, поэтому
    эти сверки — не свойство лота вообще, а свойство лота iTender.
    """

    def problems(self) -> list[str]:
        """Листинг и страница — два разбора одного лота: чем они расходятся.

        Расхождение почти всегда ошибка разбора, а не площадки: так нашёлся
        сдвиг пар на tendergarant, где «Начальная цена» съехала в «Шаг».
        """
        page = self.extra.get(LOT_SECTION) or {}
        errors = [f"нет «{label}» в «{LOT_SECTION}»" for label in REQUIRED if not page.get(label)]

        # Цена листинга — это начальная цена лота или, у публичного предложения,
        # текущая. Сравниваются числа: строки расходятся пробелами.
        prices = [
            p
            for label in ("Начальная цена, руб.", "Текущая цена, руб.")
            if (p := parse_price(page.get(label)))
        ]
        if self.price is not None and prices and not any(abs(self.price - p) < 0.005 for p in prices):
            errors.append(f"цена листинга {self.price} не равна ни начальной, ни текущей {prices}")

        for field, label in (("status_raw", "Статус"), ("lot_num", "Номер")):
            listing, detail = getattr(self, field), page.get(label)
            if listing and detail and listing != detail:
                errors.append(f"{field} листинга «{listing}» ≠ «{label}» страницы «{detail}»")
        return errors + super().problems()

    def unknown(self) -> list[str]:
        return unknown_labels(self.extra)


class TenderFogsoft(Crawler):
    """Наследнику достаточно задать ``name`` и ``DOMAIN``."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "public/purchases-all/"

    settings = BASE_SETTINGS
    params = CrawlParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # start_urls выводится из домена, чтобы не повторять путь листинга
        # в каждом из шестнадцати модулей.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def parse(self, response: Response) -> Any:
        """Листинг: раздать запросы на страницы лотов и шагнуть на следующую."""
        page = response.selector()
        num_page = response.metadata.get("page", 1)

        if num_page == 1 and not response.metadata.get("filters_reset"):
            if resets := filter_resets(page):
                button = search_button(page)
                if button is None:
                    await self.log("листинг открылся с фильтром, а кнопки поиска нет — иду как есть")
                else:
                    # Строки этой страницы отфильтрованы — их не берём: та же
                    # первая страница придёт заново уже без фильтра. Кнопка
                    # называется явно: в форме WebForms вся страница, и первая
                    # кнопка в ней — «Войти», а не «Искать».
                    await self.log("листинг открылся с фильтром — сбрасываю")
                    yield response.form_request(
                        formdata=resets, click=button, metadata={"page": 1, "filters_reset": True}
                    )
                    return

        rows = parse_rows(page)
        await self.log(f"{response.status} | страница {num_page} | лотов {len(rows)}")

        for row in rows:
            if row["lot_url"]:
                yield response.follow(row["lot_url"], callback=self.parse_lot, metadata={"row": row})

        if await paging_stops(self, num_page, [row["bids_end"] for row in rows]):
            return

        next_target = find_next_target(page, num_page)
        if next_target is None:
            await self.log(f"страница {num_page} последняя")
            return

        if not has_viewstate(page):
            # Пост без токенов сервер ответит первой страницей, и обход пошёл бы
            # по кругу. Молча выйти здесь — выдать обрыв цепочки за её конец.
            await self.log(f"страница {num_page}: токенов нет, дальше идти нечем")
            return

        # Клик по ссылке пейджера: __doPostBack кладёт её цель в __EVENTTARGET,
        # остальное — поля формы как есть.
        yield response.form_request(
            formdata={"__EVENTTARGET": next_target, "__EVENTARGUMENT": ""},
            metadata={"page": num_page + 1},
        )

    async def parse_lot(self, response: Response) -> Any:
        """Страница лота: слить строку листинга с подробностями в один айтем."""
        url = response.request.url
        match = re.search(r"/lots/view/(\d+)", url)
        if match is None:
            # Без идентификатора документ нечем ключевать в хранилище.
            await self.log(f"пропуск: в ссылке нет номера лота — {url}")
            return

        item = build_item(self.name, match.group(1), url, response.metadata["row"], response.selector())
        if not item["validation"]["ok"] and "row" in item:
            await self.log(f"лот {match.group(1)} не прошёл модель: {item['validation']['errors'][0][:120]}")
        yield item


def build_item(source: str, lot_id: str, url: str, row: dict[str, Any], page: Selector) -> dict[str, Any]:
    """Айтем лота: строка листинга и страница лота через модель ``core.lot.Lot``.

    Модель типизирует цену и сроки листинга, сводит разделы страницы в
    ``extra`` и пишет итог сверок в ``validation``. Если модель лот всё же не
    пропустила, он не теряется: без запасного документа исключение ушло бы в
    collector, тот посчитал бы ошибку, и лот не попал бы в базу вовсе — из-за
    одного поля. Запасной документ несёт ключ, сырую строку листинга и текст
    ошибки в ``validation``, чтобы разбирать его было из чего.
    """
    fetched_at = datetime.now(UTC).isoformat()
    extra, refusals = canon_detail(raw_detail(page))
    try:
        lot = FogsoftLot.model_validate(
            {
                "source": source,
                "lot_id": lot_id,
                "url": url,
                "fetched_at": fetched_at,
                "trade_id": row["trade_id"],
                "trade_number": row["trade_id"],
                "lot_num": row["lot_num"],
                "trade_type": row["trade_type"],
                # Вторая колонка листинга: в coll-temp она звалась debtor,
                # хотя там название торгов («Продажа имущества …»).
                "debtor": row["auction_name"],
                "organizer": row["organizer"],
                "winner": row["winner"],
                "description": row["description"],
                "lot_url": row["lot_url"],
                "price": parse_price(row["price"]),
                "price_raw": row["price"],
                "status": row["status"],
                "bidding_date": row["bids_end"],
                "event_date": row["auction_date"],
                "detail": extra,
                "refusals": refusals,
                "attachments": parse_attachments(page),
                "price_schedule": parse_price_schedule(page),
            }
        )
    except ValidationError as exc:
        return rejected(source, lot_id, url, fetched_at, row, exc)
    return lot.model_dump()
