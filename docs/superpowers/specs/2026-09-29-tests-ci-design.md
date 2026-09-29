# Тесты и CI

Дата: 2026-09-29. Ветка: `more-engines`.

## Цель

Покрыть тестами `src/core` и четыре движка `src/tp/{itender,kendo,btorg,ruson}`,
запускать `ruff check`, `ruff format --check` и `pytest` в GitHub Actions на
каждый push и PR.

## Границы

- `src/delete/` игнорируется: не тестируется, не проверяется ruff, не
  форматируется. Удалится позже.
- CD (деплой) — не в этой итерации: ждёт VPS.
- Код движков не меняется, кроме одного коммита `ruff format` (только
  оформление) и исправлений, если тесты найдут баги (каждое — отдельным
  коммитом с описанием).

## Старые тесты

Сломанные модули (`tests/{btorg,fogsoft,kendo,ruson}/test_*.py`,
`tests/core/test_lot.py`, `test_mongo_store.py`, `tests/test_run_all.py`) и
`tests/core/fake_mongo.py` переезжают в `src/delete/tests/` как справочник.
`tests/core/test_settings.py` и `test_detail_state.py` проверяются: рабочий и
не дублирующий новые — остаётся, иначе — в `src/delete/tests/`.
HTML-фикстуры остаются в `tests/`; фикстуры `tests/fogsoft/fixtures` — это
страницы iTender, они переезжают в `tests/itender/fixtures`.

## Раскладка

```
tests/
  conftest.py
  core/    test_help.py  test_lot.py  test_registry.py  test_storage.py  [test_settings.py]
  itender/ fixtures/  test_base.py  test_detail.py
  kendo/   fixtures/  test_base.py  test_detail.py
  btorg/   fixtures/  test_base.py  test_detail.py
  ruson/   fixtures/  test_base.py  test_detail.py
  live/    test_live.py
```

## conftest.py

- `read_fixture(path, encoding="utf-8")` — текст фикстуры (btorg — cp1251).
- `respond(crawler, request, text, status=200)` — офлайн-ответ:
  `collector.crawler.response.Response(SimpleNamespace(status_code=…, text=…, headers={}), request, crawler)`.
- `make(crawler_cls, *, params=None, sink=None)` — экземпляр краулера на
  `collector.crawler.crawler.CrawlerContext(http=None, params=…, sink=…)`.
- `collect(agen)` — список из асинхронного генератора; разделение на
  `Request` и айтемы.
- Фикстура `storage` (маркер `mongo`): `MongoStorage(source="test",
  db_name="trading_test", collection=f"test_{uuid}")` с клиентом из
  `MONGO_URI`; если `ping` не отвечает за 2 с — `pytest.skip` с причиной;
  после теста коллекция удаляется.

## Что проверяется

**core**
- `help`: `clean`, `digits`, `local_href` (http-ссылка, относительная,
  только query, голый хост), `parse_price` (пробелы, запятая, точка, хвост
  «руб», мусор), `parse_datetime` (с временем, секундами, «(34 дн.)», без
  времени, невалидная дата; пояс — Europe/Moscow).
- `lot`: computed-поля в `model_dump()`, `is_active_status` (заверш/отмен/
  признан → False; пусто, незнакомое → True; «ё»), `extra="forbid"`, `frozen`.
- `registry`: класс движка с `DOMAIN` регистрируется, без — нет;
  `detail_of(...)` не добавляет записей; дубль имени другим классом —
  `ValueError`; `platforms(Engine)` фильтрует по движку; `tp.platforms`
  даёт 32 площадки (16/5/6/5). Тестовые классы регистрируются в
  изолированном реестре (monkeypatch словаря реестра).
- `storage` (Mongo): `upsert` — новая вставка `True`, повтор `False`,
  `updated_at` не меняется без изменений и меняется при изменении;
  `pending_detail` — новые, устаревшие (`updated_at > detail_at`), не
  возвращает свежие, отдаёт `trade_url`, уважает `limit` и порядок;
  `save_detail` — пишет `detail` и `detail_at`; `detail=None` — только
  `detail_at`, прежний `detail` сохраняется; лот после этого уходит из
  `pending_detail`; `count` — только свой `source`; уникальный индекс.

**Движки** — для каждого `test_base.py`:
- чистые функции на фикстурах (листинг: число записей, поля первой;
  пейджер: следующая страница, `None` на последней, `local_href` у
  kendo/btorg; страница торгов: лоты и их поля);
- поток офлайн: `parse` отдаёт запросы торгов (callback `parse_trade`,
  metadata `trade`) и следующей страницы; `max_pages=1` — без следующей;
  `parse_trade` отдаёт dict, проходящий `Lot.model_validate`, `trade_url` и
  `lot_url` абсолютные; не-200 — `ValueError`; `start_urls` из `DOMAIN`
  (rus-on: `LISTING_PATH` у sistematorg/promkonsalt).
- iTender: `parse_rows`, `find_next_target`, `parse` (form_request на
  следующую страницу), `make_item`.

`test_detail.py`:
- `start_requests` через sink-заглушку с `pending_detail`: группировка по
  `trade_url` (fallback `lot_url`), metadata `lot_ids`; btorg — заголовок XHR;
- `parse`: детали каждому лоту; btorg/rus-on — лот, которого нет на
  странице, получает `detail: None`; kendo — страница без `#main-info` —
  `ValueError`; iTender — `parse_detail` на фикстурах fogsoft
  (разделы, списки из гридов, распорки tdContent);
- `detail_of`: MRO, `name`, `params` детального класса, модуль площадки.

**Новые фикстуры**, если найдутся на живых площадках: btorg-аукцион без
графика цены и с пустым «Предмет торгов»; kendo-листинг с карточками лотов
(`<div>`). Не нашлись — тесты на эти ветки не пишутся, это отмечается.

**live** (маркер `live`, не в CI, `pytest -m live`): по площадке на движок
(centerr, trade_alliance, atctrade, rus_on) — base с `max_pages=1` даёт ≥ 1
лот без ошибок, detail на 1 лот даёт детали; без Mongo (sink-заглушка).

## pyproject.toml

```toml
[tool.ruff]
extend-exclude = ["src/delete"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
addopts = "-m 'not live'"
markers = [
    "mongo: нужна запущенная Mongo (MONGO_URI), без неё — skip",
    "live: ходит на реальные площадки, не в CI",
]
```

## Форматирование

Отдельным коммитом до тестов: `ruff format src/core src/tp tests` — только
оформление (в том числе iTender: `kw = 1` → `kw=1`, кавычки). Затем
`ruff check --fix` для импортов.

## CI — `.github/workflows/ci.yml`

- `on: push` (все ветки) и `pull_request` в `main`.
- job `lint`: checkout → `astral-sh/setup-uv` (кэш) → `uv sync --locked` →
  `uv run ruff check` → `uv run ruff format --check`.
- job `test`: `services.mongo` (`mongo:8`, порт 27017, healthcheck
  `mongosh --eval "db.adminCommand('ping')"`) → checkout → setup-uv →
  `uv sync --locked` → `uv run pytest` с `MONGO_URI=mongodb://localhost:27017`.
  В CI mongo-тесты не должны скипаться: переменная `REQUIRE_MONGO=1`
  превращает skip в ошибку.
- Python — из `.python-version` (3.12). collector-framework — публичный git,
  токен не нужен.

## Проверка

Локально: `uv run ruff check`, `uv run ruff format --check`, `uv run pytest`
(с поднятой Mongo — без skip), `uv run pytest -m live` (с VPN-исключениями).
CI: зелёный прогон на push ветки.
