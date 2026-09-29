# trading_platform

Парсеры площадок банкротных торгов поверх
[collector-framework](https://github.com/barabacker/collector-framework).
32 площадки на четырёх движках, результат — в MongoDB.

| движок | площадок | площадки |
|---|---|---|
| iTender | 16 | alfalot, arbbitlot, arbitat, bep, centerr, etb, etpu_bankrupt, etpugra, gloria_service, meta_invest, tender_one, tendergarant, utender, utp_lot, yuzhnyy_etp, zakazrf |
| Kendo-ETP | 7 | trade_alliance, seltim, electro_torgi, torgi82, vetp, etp_profit, ptp_center |
| btorg (edoc-ETP) | 4 | atctrade, ausib, aukcioncenter, regtorg |
| rus-on | 5 | nistp, el_torg, rus_on, sistematorg, promkonsalt |

## Быстрый старт

```bash
uv sync                                   # зависимости
docker compose up -d                      # Mongo на 127.0.0.1:27017
uv run python -m tp.scripts.crawl         # листинги всех площадок, до 30 страниц
uv run python -m tp.scripts.detail        # детали лотов, которые их ждут
```

## Запуск

Сбор идёт в два прохода: **листинг** (какие лоты есть, цена, статус, сроки) и
**детали** (страница лота или торгов целиком). Детали запрашиваются только
для лотов, которые их ждут: новых и изменившихся в листинге после прошлых
деталей — это решает база, отдельного состояния нет.

```bash
uv run python -m tp.scripts.crawl                         # все площадки, до 30 страниц листинга
uv run python -m tp.scripts.crawl kendo atctrade          # движок и отдельная площадка вперемешку
uv run python -m tp.scripts.crawl --max-pages 5
uv run python -m tp.scripts.detail                        # до 100 лотов на площадку за прогон
uv run python -m tp.scripts.detail rus_on --limit 500
uv run python -m tp.scripts.crawl --list                  # движки и площадки
uv run python -m tp.scripts.crawl -v                      # плюс логи фреймворка, по запросу
```

Имена — площадки или движки (`itender`, `kendo`, `btorg`, `ruson`); без имён —
все. Площадки идут параллельно (не больше `PLATFORM_CONCURRENCY`), упавшая не
останавливает остальные. В конце — таблица по площадкам: сколько лотов
(деталей), новых (снятых с торгов), ошибок, время, причина остановки. Код
выхода 1, если площадка упала — исключением или ошибками при пустом
результате (недоступна, переехала, сменила разметку).

Сеть: площадки — российские; с VPN их адреса нужно держать в исключениях
(адреса у площадок меняются — `meta-invest.ru` так уже переезжал).

## База

```bash
docker compose up -d          # поднять Mongo на 127.0.0.1:27017
docker compose ps             # убедиться, что healthcheck зелёный
docker compose down           # остановить, данные останутся в томе mongo-data
docker compose down -v        # остановить и стереть собранное
docker compose --profile tools up -d    # mongo-express на 127.0.0.1:8081
```

Коллекция одна на все площадки — `trading.lots`; площадку различает поле
`source`, ключ документа — `(source, lot_id)`. Уникальный индекс по нему
создаёт сам код при открытии хранилища.

Документ лота:

- поля листинга. У Kendo, btorg и rus-on — модель `core.lot.Lot`: значения
  как на площадке (`price`, `bids_end`, `auction_date`, `status` — строки) и
  разобранные рядом (`price_value`, `bids_end_at`, `auction_at` — по Москве,
  `is_active` — по статусу). iTender пишет те же поля строкой листинга, без
  разобранных;
- `lot_url` — страница лота для человека (если своей нет — страница торгов),
  `trade_url` — откуда detail берёт детали (страница торгов или AJAX-фрагмент
  лотов btorg);
- `created_at`, `updated_at` — ставит хранилище; `updated_at` сдвигается,
  только когда лот изменился на площадке (обычно статус);
- `detail`, `detail_at` — дописывает detail. Вид `detail` — свой у движка:
  разделы с парами у iTender, пары «подпись: значение» у остальных, плюс
  `attachments` (Kendo) и `price_schedule` — график снижения цены (btorg,
  rus-on). Лот, которого на странице торгов уже нет, получает только
  `detail_at`: прежние детали остаются, в очередь он не возвращается.

```bash
docker compose exec mongo mongosh trading --eval 'db.lots.countDocuments({source: "bep"})'
```

## Настройки

Окружение читается в одном месте — `core/conf.py` на `pydantic-settings`.
Умолчания подобраны так, что без единой переменной работает локальная Mongo
из `compose.yaml`. Берётся из окружения и из `.env` в корне; переменные
окружения приоритетнее файла.

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | адрес базы |
| `MONGO_DB` | `trading` | имя базы |
| `MONGO_COLLECTION` | `lots` | коллекция, общая на все площадки |
| `MAX_PAGES` | `100` | предел страниц листинга по умолчанию у движков; скрипт `crawl` задаёт свой (`--max-pages`, 30) |
| `DELAY` | `0.5` | пауза между запросами к одной площадке, с |
| `PLATFORM_CONCURRENCY` | `16` | сколько площадок обходить разом |
| `HTTP_TIMEOUT` | `60` | таймаут запроса, с |
| `SINCE` | — | окно по дате `ГГГГ-ММ-ДД`; пока не используется |

## Устройство

```
src/
  core/                     общее без привязки к движку
    conf.py                 настройки из окружения и .env
    help.py                 разбор значений: пробелы, цена, дата по Москве, ссылки
    lot.py                  модель лота листинга Lot
    registry.py             реестр площадок: имя -> класс
    deps.py                 open_run: хранилище и обход одного прогона
    db/                     Store — интерфейс, MongoStorage — реализация
    hooks/                  хуки HTTP (inprotect)
    certs/                  недостающие звенья TLS-цепочек площадок
  tp/
    <движок>/               itender, kendo, btorg, ruson
      base.py               обход листинга: чистые функции разбора + краулер движка
      detail.py             детали лота: разбор страницы + примесь detail_of(площадка)
      source.py             площадки движка
    platforms.py            импорт всех площадок — заполняет реестр
    scripts/                crawl, detail и общее для них
  delete/                   прежние парсеры и скрипты — справочник, удалится
tests/
  conftest.py               офлайн-ответы краулеру, хранилище на Mongo
  core/ itender/ kendo/ btorg/ ruson/ scripts/   тесты по разделам, фикстуры — в <движок>/fixtures
  live/                     живые тесты по площадке на движок
```

Площадка — несколько строк в `tp/<движок>/source.py`; в реестр её заносит
базовый класс движка, стоит объявить `DOMAIN`:

```python
class Seltim(Kendo):
    name = "seltim"
    DOMAIN = "https://bankrupt.seltim.ru"
```

Особенности площадки — в её классе: свои `settings` (хук антибота, свой
сертификат, `skip_tls_verify`), свой `LISTING_PATH`. Имя площадки уникально
между движками — повтор даёт ошибку при импорте.

## Разработка

```bash
uv run pytest                 # офлайн-тесты; тесты хранилища — на Mongo из compose
uv run pytest -m live         # живые тесты: реальные площадки, по одной на движок
uv run ruff check
uv run ruff format
```

Без Mongo тесты хранилища пропускаются; с `REQUIRE_MONGO=1` — падают (так в CI).

CI — GitHub Actions (`.github/workflows/ci.yml`): на каждый push и PR в
`main` — `ruff check`, `ruff format --check` и `pytest` с Mongo 8. Живые тесты
в CI не идут: площадки с раннеров GitHub недоступны.
