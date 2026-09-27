# trading_platform

Парсеры площадок банкротных торгов поверх
[collector-framework](https://github.com/barabacker/collector-framework).
32 площадки на четырёх движках, по файлу на площадку, результат — в MongoDB:

| движок | площадок | пакет |
|---|---|---|
| iTender (fogsoft) | 16 | `tp.fogsoft_platform` |
| Kendo-ETP | 5 | `tp.kendo_platform` |
| btorg (edoc-ETP) | 6 | `tp.btorg_platform` |
| rus-on | 5 | `tp.ruson_platform` |

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
площадке), `is_active` — из статуса. Страница лота — в `extra` как есть:
у iTender это разделы с подписями, у остальных движков — плоский словарь.
Документы — в `attachments`, график снижения цены — в `price_schedule`.
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
uv sync                                      # зависимости
uv run python -m run_all                     # все площадки разом
uv run python -m run_all centerr etb         # только названные
uv run python -m run_all --max-pages 2       # короткий прогон
uv run python -m run_all --since 2026-06-01  # окно по дате
uv run python -m run_all --max-errors 200    # терпимость к сбоям на прогон
uv run python -m run_all --list              # что вообще есть
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
run_all.py                обход площадок: запуск, прогресс, итоговая таблица
core/settings.py          настройки из окружения и .env
core/db/                  Store — интерфейс, MongoStore — реализация
tp/common.py              общее для всех движков: настройки HTTP, параметры прогона
tp/base.py                iTender (fogsoft): разбор, пагинация через форму, обход
tp/dive.py                Kendo, btorg, rus-on: листинг торгов -> заход в торги -> лоты
tp/{kendo,btorg,ruson}.py разбор этих трёх движков
tp/*_platform/*.py        по файлу на площадку: имя, домен, особенность
tp/hooks/                 сквозные обязанности (проверка inprotect)
tp/certs/                 недостающие звенья TLS-цепочек
```

Площадка — это несколько строк в пакете своего движка:

```python
class Centerr(TenderFogsoft):
    name = "centerr"
    DOMAIN = "https://bankrupt.centerr.ru"
```

Окно `--since` работает по сроку приёма заявок из листинга. На btorg его нет —
только начало приёма, — и там окно не действует: остановка по началу теряла
бы торги, начатые раньше окна и ещё идущие.

## Разработка

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```
