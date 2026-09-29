# Перенос движков kendo, btorg, rus-on на схему iTender

Дата: 2026-09-29. Ветка: `more-engines`.

## Цель

Парсеры из `src/tp/delete/` (kendo, btorg, rus-on) переработать по образцу
`src/tp/itender/`: `base.py` — обход листинга, `detail.py` — детали лота,
`source.py` — площадки. Общая pydantic-модель лота — `src/core/lot.py`.

## Границы

- `src/tp/itender/` не меняется.
- `src/tp/delete/` не меняется: остаётся справочником и резервной копией,
  удаляется отдельно после окончания работы.
- fogsoft не переносится — это тот же движок, что iTender.
- Фильтр по статусу (`delete/search.py`) не переносится: листинг листается
  подряд до `params.max_pages`, как у iTender.
- Скрипты запуска не добавляются (будут воркеры).
- Тесты — отдельным этапом после кода. Старые тесты не трогаются.

## Раскладка

```
src/core/
  lot.py      новый: Lot, is_active_status
  help.py     дополнен: parse_price, parse_datetime (Europe/Moscow)
src/tp/
  kendo/  __init__.py base.py detail.py source.py   5 площадок
  btorg/  __init__.py base.py detail.py source.py   6 площадок
  ruson/  __init__.py base.py detail.py source.py   5 площадок
```

Площадки — те же, что в `delete/*_platforms.py`:

- kendo: trade_alliance, seltim, electro_torgi, torgi82, vetp
- btorg: atctrade, ausib, etp_profit, aukcioncenter, regtorg, ptp_center
- ruson: nistp, el_torg, rus_on, sistematorg, promkonsalt

В `source.py` — класс на площадку (`name`, `DOMAIN`, при необходимости свои
`settings`) и словарь `PLATFORMS: dict[str, type[<Движок>]]`, как в
`itender/source.py`.

## core/lot.py

Модель взята из коммита `f7731c9` (`src/core/lot.py`):

```python
class Lot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    lot_id: str
    lot_url: str
    trade_url: str | None = None

    trade_id: str | None = None
    trade_number: str | None = None
    trade_type: str | None = None
    auction_name: str | None = None
    lot_num: str | None = None
    description: str | None = None
    organizer: str | None = None
    debtor: str | None = None
    winner: str | None = None

    price: str | None = None         # как на площадке
    bids_end: str | None = None      # окончание приёма заявок, как на площадке
    auction_date: str | None = None  # дата торгов, как на площадке
    status: str | None = None

    # computed_field, попадают в model_dump():
    price_value: float | None        # parse_price(price)
    bids_end_at: datetime | None     # parse_datetime(bids_end), МСК
    auction_at: datetime | None      # parse_datetime(auction_date), МСК
    is_active: bool                  # is_active_status(status)
```

- Имена полей — как в строке листинга iTender.
- `extra="forbid"`: опечатка в имени поля — сразу `ValidationError`.
- Детали лота в модель не входят: их пишет `Store.save_detail` в поле `detail`.
- `is_active_status`: статус без маркеров завершения («заверш», «состоял»,
  «отмен», «приостановлен», «аннулирован», «признан», «окончен») — активен;
  пустой или незнакомый — тоже активен.
- `parse_price` и `parse_datetime` добавляются в `core/help.py`:
  `parse_price("1 234 567,89") == 1234567.89`, нечисловое — `None`;
  `parse_datetime("28.10.2026 10:00 (34 дн.)")` — datetime в Europe/Moscow,
  дата без времени — полночь, нераспознанное — `None`.

## base.py — листинг → торги → Lot

Класс движка (`Kendo`, `Btorg`, `Ruson`) наследует `collector.Crawler`:

- `DOMAIN`, `LISTING_PATH`, `settings`, `params` (dataclass с `max_pages`),
  `__init_subclass__` собирает `start_urls` из `DOMAIN` — как у `ITender`.
- `parse(response)` — страница листинга: не-200 — `ValueError`; для каждых
  торгов `response.follow(..., callback=self.parse_trade, metadata={"trade": …})`;
  затем следующая страница, если она есть и `num_page < params.max_pages`.
- `parse_trade(response)` — страница торгов: по `Lot(...).model_dump()` на лот.
  `lot_id = f"{trade_id}_{lot_num}"`, `trade_url` — адрес страницы торгов
  (у btorg — AJAX-фрагмента), `lot_url` — страница лота, если есть, иначе
  страница торгов.
- В base не кладётся ничего из деталей (main-info, документы, график снижения
  цены) и ничего, что меняется на каждом обходе (`fetched_at` и т. п.): иначе
  `updated_at` лота сдвигался бы каждый прогон и детали перечитывались бы зря.

Разбор — чистые функции модуля, перенесённые из `delete/<движок>.py`:

| движок | листинг | пейджер | страница торгов |
|---|---|---|---|
| kendo | `/lots`, карточки `block-lot`, ссылка «Номер торгов» | `ul.pagination`, `?page=N` | `div#lots` — лоты, `div#main-info` — организатор, сроки |
| btorg | `/etp/trade/list.html`, `table.data` | `list.html?page=N` | AJAX `inner-view-lots.html` (заголовок XHR), `table#lotNumberN` |
| ruson | `table.data` / `table.node_view`, ссылка `trade_view.php?trade_nid=N`, колонки по заголовку | `pagenum` | пары `<td>подпись</td><td>значение</td>`, таблицы «Лот № N» |

Особенности движков сохраняются: у btorg — сроки из графика снижения цены и
описание из «Сведения об имуществе…», если «Предмет торгов» пуст; у rus-on
номер страницы — поле формы `pagenum`. Там, где старый код брал поле
листинга из формы поиска, запрос страницы строится без поля статуса.

## detail.py — pending_detail → страница торгов → detail

Как у iTender: примесь `<Движок>Detail(<Движок>)` и
`detail_of(platform) -> type[<Движок>Detail]`, модуль класса — модуль площадки.

- `params = DetailParams(limit=100)`.
- `start_requests`: лоты из `self.ctx.sink.pending_detail(self.params.limit)`,
  группировка по `trade_url` (для лота без `trade_url` — `lot_url`); на
  страницу торгов — один запрос, в `metadata` — `lot_id` ожидающих лотов.
- `parse`: не-200 — `ValueError`; иначе для каждого ожидающего лота этих торгов
  `{"lot_id": …, "detail": {…}}`.
- `detail` — словарь: пары «подпись: значение» (сведения о торгах и о лоте),
  `attachments` — `[{"name", "url"}]`, где есть, `price_schedule` —
  `[{заголовок: ячейка}]`, где есть (btorg).

Изменение в хранилище: `MongoStorage.pending_detail` отдаёт в проекции ещё и
`trade_url`. iTender на это не завязан (у его лотов поля нет — ключа не будет).

## Ошибки

- Ответ не 200 — `ValueError`, дальше — `max_errors` из `settings` фреймворка.
- Неверное поле `Lot` — `ValidationError` на первом же айтеме.
- Лот, чья страница деталей не открылась, не получает `detail_at` и попадает в
  `pending_detail` снова.

## Проверка

Тесты — следующим этапом. На этом этапе: `ruff check src` и ручной прогон
base и detail одной площадки каждого движка с `max_pages=1` скриптом из
scratchpad (скрипты в репозиторий не добавляются).
