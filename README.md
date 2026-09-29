# trading_platform

Парсеры площадок банкротных торгов поверх
[collector-framework](https://github.com/barabacker/collector-framework).
32 площадки на четырёх движках, по файлу на площадку, результат — в MongoDB:

| движок | площадок | код |
|---|---|---|
| iTender (fogsoft) | 16 | `tp/itender` |
| Kendo-ETP | 5 | `tp/kendo` |
| btorg (edoc-ETP) | 6 | `tp/btorg` |
| rus-on | 5 | `tp/ruson` |

## База

```bash
docker compose up -d          # поднять Mongo на 127.0.0.1:27017
docker compose ps             # убедиться, что healthcheck зелёный
docker compose down           # остановить, данные останутся в томе mongo-data
docker compose down -v        # остановить и стереть собранное
```

Коллекция одна на все площадки — `trading.lots`, площадку различает поле
`source`, ключ документа — `(source, lot_id)`. Уникальный индекс по этому
ключу создаёт сам код при открытии хранилища, отдельной миграции нет.

Документ листинга — модель `core.lot.Lot`, общая для всех движков: поля
названы как у строки листинга iTender, значения — строками, как на площадке
(`price`, `bids_end`, `auction_date`, `status`), рядом — разобранные
(`price_value`, `bids_end_at`, `auction_at` — по Москве, `is_active` — из
статуса). Детали лота детальный парсер дописывает в `detail` с отметкой
`detail_at`: у всех движков это разделы с парами «подпись: значение».
Хранилище добавляет `created_at` и `updated_at`; `updated_at` сдвигается,
только если лот изменился.

Посмотреть собранное глазами:

```bash
docker compose --profile tools up -d    # mongo-express на 127.0.0.1:8081
```

Или из консоли:

```bash
docker compose exec mongo mongosh trading --eval 'db.lots.countDocuments({source: "bep"})'
```

## Обход

```bash
uv sync                                      # зависимости
uv run python -m run_all                     # все площадки разом
uv run python -m run_all centerr etb         # только названные
uv run python -m run_all --max-pages 2       # короткий прогон
uv run python -m run_all --since 2026-06-01  # окно по дате
uv run python -m run_all --max-errors 200    # терпимость к сбоям на прогон
uv run python -m run_all --list              # что вообще есть
uv run start_kendo --max-pages 2             # только площадки одного движка
```

`start_fogsoft`, `start_kendo`, `start_btorg`, `start_ruson` — тот же
`run_all` с теми же флагами, но с площадками только своего движка. Это
`tp/run_<движок>.py`: `uv run python -m tp.run_kendo` делает то же самое.

## Настройки

Всё окружение читается в одном месте — `core/conf.py` на `pydantic-settings`.
Значения по умолчанию подобраны так, что без единой переменной работает
локальная Mongo из `compose.yaml`.

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | адрес базы |
| `MONGO_DB` | `trading` | имя базы |
| `MONGO_COLLECTION` | `lots` | коллекция, общая на все площадки |
| `MAX_PAGES` | `100` | предохранитель: страниц листинга на площадку |
| `SINCE` | — | окно по дате `ГГГГ-ММ-ДД`: листать, пока на странице есть лот с приёмом заявок не раньше неё |
| `DELAY` | `0.5` | пауза между запросами к одной площадке, с |
| `PLATFORM_CONCURRENCY` | `16` | сколько площадок обходить разом |
| `HTTP_TIMEOUT` | `60` | таймаут запроса, с |

Берётся из окружения и из `.env` в корне; переменные окружения приоритетнее
файла, чтобы настройки CI или docker не перетирались чьим-то локальным `.env`.

## Устройство

```
src/
  core/                   общее без привязки к движку
    conf.py               настройки из окружения и .env
    help.py               разбор значений: пробелы, цена, дата
    lot.py                Lot — общая pydantic-модель лота листинга
    deps.py               open_run: хранилище и обход одним контекстом
    db/                   Store — интерфейс, MongoStorage — реализация
    hooks/                сквозные обязанности (проверка inprotect)
    certs/                недостающие звенья TLS-цепочек
  tp/
    common.py             общее для Kendo, btorg, rus-on: поиск по статусу
                          GET-формой и детали со страницы торгов
    <движок>/
      base.py             базовый парсер: обход листинга, айтемы лотов
      detail.py           детальный парсер: лоты, ждущие деталей, -> detail
      source.py           площадки движка: класс, домен, настройки; PLATFORMS
    scripts/              отладочные прогоны iTender
tests/
  core/ kendo/ btorg/ ruson/            тесты по разделам кода,
                                        фикстуры — в <раздел>/fixtures
```

Площадка — это класс в `tp/<движок>/source.py`:

```python
class Seltim(Kendo):
    name = 'seltim'
    DOMAIN = 'https://bankrupt.seltim.ru'
    settings = Settings(...)
    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)
```

Детальный парсер площадки — `detail_of(Seltim)` из `tp/<движок>/detail.py`:
какие лоты обходить (новые и изменившиеся после деталей), решает база.

У Kendo, btorg и rus-on листинг перечисляет торги, а лоты — только на
странице торгов, поэтому базовый парсер ищет по статусам (`statuses`,
названия через запятую, по умолчанию актуальные) и заходит в каждые торги.
Детали лота берутся со страницы торгов (`trade_url` лота): один запрос на
торги отдаёт детали всех её лотов.

## Разработка

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```
