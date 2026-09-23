# trading_platform

Парсеры площадок банкротных торгов на движке iTender (fogsoft) поверх
[collector-framework](https://github.com/barabacker/collector-framework).
Шестнадцать площадок, по файлу парсера на площадку, результат — в MongoDB.

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

Документ — модель `core.lot.Lot` (перенесена из coll-temp): поля листинга,
цена и сроки разобраны (`price`, `bidding_deadline`, `result_date` — по Москве,
сырые строки рядом), статус сведён к одному написанию (`status_raw` — как на
площадке), `is_active` — из статуса. Страница лота — в `extra` как есть,
документы — в `attachments`, график снижения цены — в `price_schedule`.
Хранилище добавляет `first_seen_at`, `last_seen_at` и `run_id` запуска: лот,
чей `run_id` отстал от последнего, последним обходом не увиден.

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
uv sync                                                # зависимости
uv run python -m tp.platform.run_all                   # все площадки разом
uv run python -m tp.platform.run_all centerr etb       # только названные
uv run python -m tp.platform.run_all --max-pages 2     # короткий прогон
uv run python -m tp.platform.run_all --since 2026-06-01 # окно по дате
uv run python -m tp.platform.run_all --list            # что вообще есть
uv run python -m tp.platform.bep                       # одна площадка отдельно
```

## Настройки

Всё окружение читается в одном месте — `core/settings.py` на `pydantic-settings`.
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
core/settings.py      настройки из окружения и .env
core/db/              Store — интерфейс, MongoStore — реализация
tp/base.py            TenderFogsoft: разбор, пагинация, обход
tp/platform/*.py      по файлу на площадку: имя, домен, особенность
tp/hooks/             сквозные обязанности (проверка inprotect)
tp/certs/             недостающие звенья TLS-цепочек
```

Площадка — это несколько строк:

```python
class Centerr(TenderFogsoft):
    name = "centerr"
    DOMAIN = "https://bankrupt.centerr.ru"
```

## Разработка

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```
