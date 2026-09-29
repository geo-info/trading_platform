# Раннер: мост между control plane и collector-framework — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Раннер, который забирает задания у Django-control plane (`dashboard`), исполняет их парсерами на `collector-framework`, пишет айтемы в JSONL и отчитывается счётчиками и логами.

**Architecture:** Четыре независимых модуля и клей. `parsers` знают только `collector`; `storage` принимает dict и отдаёт путь; `control` говорит по HTTP; `runner` их склеивает. Айтемы вычерпывает раннер через `crawler.stream()`, поэтому парсеры не переопределяют `process_item()` и остаются такими, какими их пишут по документации фреймворка.

**Tech Stack:** Python 3.11+, uv, `collector-framework`, `httpx`, `pytest` + `pytest-asyncio`, ruff.

**Спека:** `docs/superpowers/specs/2026-09-18-runner-collector-integration-design.md`

---

## Что известно про чужой код

Читать исходники по ходу не нужно — вот всё, на что опирается план.

**Control plane** (`http://127.0.0.1:8000`), заголовок `X-Runner-Token`:

| Эндпоинт | Запрос | Ответ |
|---|---|---|
| `POST /api/v1/runs/claim/` | пусто | `{"run": null, "poll_interval": 10}` или `{"run": {"id", "source", "parser", "params", "log_level", "trigger", "lease_expires_at"}, "poll_interval": 10}` |
| `POST /api/v1/runs/<id>/logs/` | `{"entries": [{"ts", "level", "message", "context"}]}` | `{"accepted": N}` |
| `POST /api/v1/runs/<id>/heartbeat/` | пусто | `{"lease_expires_at": "..."}` |
| `POST /api/v1/runs/<id>/complete/` | `{"status": "success"\|"failed", "counters": {}, "result_locator": "", "error": ""}` | `{"id", "status", "source_active"}` |

`seq` для логов проставляет сервер. Пачка — не больше 500 строк. Из `counters` сервер понимает `items_total`, `items_new`, `items_updated`; всё остальное складывает в JSON-поле.

**Фреймворк** (`from collector import ...`):

```python
open_crawler(parser_cls, *, params: dict[str, str], sink, log) -> AsyncIterator[Crawler]
crawler.stream()  # async-итератор айтемов
crawler.stats     # Stats(requests, errors, items, started_at, finished_at, reason); .elapsed — property
crawler.errors    # list[tuple[Request, Exception]]
```

Два поведения фреймворка, на которых стоит вся обработка отказов:

1. `Crawler.run()` в конце делает `raise self.errors[0][1]`, если была хоть одна ошибка. То есть **одна упавшая страница роняет весь краул** — но айтемы, отданные до этого, уже вычерпаны и записаны. Исключение несёт `exc.crawler` с `.errors` и `.stats`.
2. `break` из `async for ... in crawler.stream()` останавливает краул, и `stats.reason` становится `'cancelled'`. Это штатный путь, им и реализуется мягкая остановка по Ctrl+C.

`Parser.log(msg)` зовёт `ctx.log(msg)` — голая строка без уровня. Параметры фреймворк читает как `params.get('concurrency')` / `params.get('max_requests')`, то есть строками.

## Структура файлов

| Файл | Ответственность |
|---|---|
| `pyproject.toml` | зависимости, ruff, pytest |
| `Makefile` | команды разработки |
| `.env.example` | шаблон окружения |
| `.github/workflows/ci.yml` | линтер + тесты |
| `src/trading/parsers/quotes.py` | парсер `quotes` |
| `src/trading/parsers/__init__.py` | `REGISTRY`, `resolve()`, `UnknownParser` |
| `src/trading/storage/jsonl.py` | `JsonlSink` |
| `src/trading/control/client.py` | `ControlClient` |
| `src/trading/runner/config.py` | `Config.from_env()`, `load_env_file()` |
| `src/trading/runner/logs.py` | `LogBuffer`, `LogBufferHandler` |
| `src/trading/runner/execute.py` | `coerce_params()`, `counters_from()`, `execute_run()` |
| `src/trading/runner/loop.py` | `run_forever()`, обработка SIGINT |
| `src/trading/runner/__main__.py` | точка входа |
| `tests/conftest.py` | локальный HTTP-сервер с фикстурой |
| `tests/test_*.py` | по модулю на файл |

Сеть в тестах не используется: краул ходит на `http.server`, поднятый в потоке на случайном порту; control plane изображает `httpx.MockTransport`.

---

### Task 1: Скелет репозитория

Тестов нет — это леса. Конвенции зеркалят `dashboard`.

**Files:**
- Create: `pyproject.toml`, `Makefile`, `.env.example`, `.github/workflows/ci.yml`
- Create: `src/trading/__init__.py`, `src/trading/parsers/__init__.py`, `src/trading/storage/__init__.py`, `src/trading/control/__init__.py`, `src/trading/runner/__init__.py`, `tests/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Создать `pyproject.toml`**

```toml
[project]
name = "trading-platform"
version = "0.1.0"
description = "Раннер парсеров для control plane"
requires-python = ">=3.11"
dependencies = [
    "collector-framework>=0.0.1",
    "httpx>=0.27",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.9",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/trading"]

[tool.ruff]
line-length = 110
target-version = "py311"
exclude = [".venv", "*.md"]
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "C4"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["trading"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
```

`asyncio_mode = "auto"` избавляет от `@pytest.mark.asyncio` на каждом async-тесте. `pythonpath = ["src"]` даёт импорт `trading` без установки пакета.

- [ ] **Step 2: Создать пустые пакеты**

```bash
mkdir -p src/trading/parsers src/trading/storage src/trading/control src/trading/runner tests
touch src/trading/__init__.py src/trading/storage/__init__.py src/trading/control/__init__.py src/trading/runner/__init__.py tests/__init__.py
```

`src/trading/parsers/__init__.py` не создаём пустым — он появится в Task 2 сразу с содержимым.

- [ ] **Step 3: Создать `Makefile`**

```makefile
.DEFAULT_GOAL := help

UV ?= uv
RUN := $(UV) run

.PHONY: help install sync lock upgrade run test lint fmt ci clean distclean

help: ## Показать список команд
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Поставить зависимости по uv.lock (создаст .venv)
	$(UV) sync

sync: ## То же, но строго по локу — ничего не перерешает
	$(UV) sync --locked

lock: ## Пересобрать uv.lock после правок pyproject.toml
	$(UV) lock

upgrade: ## Поднять версии зависимостей в пределах ограничений
	$(UV) lock --upgrade

run: ## Запустить раннер
	$(RUN) python -m trading.runner

test: ## Прогнать тесты
	$(RUN) pytest -v

lint: ## Проверить код линтером
	$(RUN) ruff check .
	$(RUN) ruff format --check .

fmt: ## Отформатировать код и исправить автопочинимое
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

ci: lint test ## Всё, что гоняет CI

clean: ## Удалить кэши
	find . -path ./.venv -prune -o -name '__pycache__' -type d -print0 | xargs -0 rm -rf
	rm -rf .ruff_cache .pytest_cache

distclean: clean ## Удалить ещё и venv с данными
	rm -rf .venv data
```

- [ ] **Step 4: Создать `.env.example`**

```bash
# Скопируйте в .env и правьте под себя: cp .env.example .env
# Файл .env в git не попадает; переменные окружения имеют приоритет над ним.

# Адрес control plane
CONTROL_URL=http://127.0.0.1:8000
# Токен раннера из админки: Парсеры -> Раннеры
RUNNER_TOKEN=
# Корень для JSONL-файлов
DATA_DIR=data
# Запасной интервал опроса, если ответ claim его не дал
POLL_INTERVAL=10
# Таймаут запросов к control plane, с
HTTP_TIMEOUT=30
# Как часто отправлять накопленные строки лога, с
LOG_FLUSH_SECONDS=2
```

- [ ] **Step 5: Дописать `.gitignore`**

Добавить в конец файла:

```
# Данные парсеров и локальное окружение
/data/
.env
```

- [ ] **Step 6: Создать `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

env:
  UV_FROZEN: "1"

jobs:
  lint:
    name: Линтер
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - run: uv sync --locked
      - name: ruff check
        run: uv run ruff check .
      - name: ruff format --check
        run: uv run ruff format --check .

  test:
    name: Тесты (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
          python-version: ${{ matrix.python-version }}
      - run: uv sync --locked
      - name: Тесты
        run: uv run pytest -v
```

- [ ] **Step 7: Поставить зависимости и убедиться, что окружение собирается**

Run: `uv lock && uv sync`
Expected: создан `.venv`, создан `uv.lock`, в выводе есть `collector-framework` и `httpx`.

Run: `uv run python -c "import collector, httpx; print(collector.__version__)"`
Expected: `0.0.1`

- [ ] **Step 8: Коммит**

```bash
git add pyproject.toml uv.lock Makefile .env.example .gitignore .github src tests
git commit -m "Скелет репозитория раннера: uv, ruff, pytest, CI"
```

---

### Task 2: Реестр парсеров и парсер quotes

**Files:**
- Create: `src/trading/parsers/quotes.py`
- Create: `src/trading/parsers/__init__.py`
- Test: `tests/test_parsers.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_parsers.py`:

```python
import pytest

from trading.parsers import REGISTRY, UnknownParser, resolve


def test_resolve_returns_parser_class():
    parser_cls = resolve("quotes")
    assert parser_cls.name == "quotes"
    assert parser_cls.start_urls == ["https://quotes.toscrape.com/"]


def test_resolve_unknown_key_lists_known_ones():
    with pytest.raises(UnknownParser) as exc_info:
        resolve("нет-такого")

    message = str(exc_info.value)
    assert "нет-такого" in message
    assert "quotes" in message


def test_registry_keys_match_parser_names():
    """Ключ реестра — контракт с админкой, но расходиться с name он не должен."""
    for key, parser_cls in REGISTRY.items():
        assert key == parser_cls.name
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `uv run pytest tests/test_parsers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading.parsers'` или `ImportError: cannot import name 'REGISTRY'`

- [ ] **Step 3: Написать парсер**

Создать `src/trading/parsers/quotes.py`:

```python
"""Пагинация: идём по цепочке страниц, на каждую цитату — айтем.

Форма, которая покрывает большинство скрейпов. ``parse()`` отдаёт айтемы,
а затем следующий запрос, так что обход идёт по одной странице за раз:
страница N+1 известна только после разбора страницы N.
"""

from __future__ import annotations

from typing import Any

from collector import Parser, Response, Settings


class Quotes(Parser):
    name = "quotes"
    start_urls = ["https://quotes.toscrape.com/"]
    settings = Settings(delay=0.5)

    async def parse(self, response: Response) -> Any:
        page = response.selector()

        for quote in page.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(),
                "author": quote.css("small.author::text").get(),
                "tags": quote.css("div.tags a.tag::text").getall(),
            }

        next_page = page.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page)
```

Это пример из репозитория фреймворка, из которого убраны `main()` и настройка консоли. `process_item()` не переопределён и переопределяться не должен: айтемы вычерпывает раннер.

- [ ] **Step 4: Написать реестр**

Создать `src/trading/parsers/__init__.py`:

```python
"""Реестр парсеров: ключ из админки -> класс.

Ключ словаря — публичный контракт с control plane (поле «парсер» у источника),
а не путь в Python. Класс можно переименовать, не трогая данные в чужой базе.

Автодискавери по подклассам сознательно нет: импорт-сайдэффекты и молчаливые
коллизии имён, а «почему парсер не виден» — худший жанр отладки.
"""

from __future__ import annotations

from collector import Parser

from trading.parsers.quotes import Quotes

__all__ = ["REGISTRY", "UnknownParser", "Quotes", "resolve"]

REGISTRY: dict[str, type[Parser]] = {
    "quotes": Quotes,
}


class UnknownParser(LookupError):
    """В реестре нет парсера с таким ключом."""


def resolve(key: str) -> type[Parser]:
    """Класс парсера по ключу из задания.

    Неизвестный ключ — это опечатка в админке, и сообщение должно её закрывать:
    называем ключ и перечисляем то, что есть.
    """
    try:
        return REGISTRY[key]
    except KeyError:
        known = ", ".join(sorted(REGISTRY)) or "реестр пуст"
        raise UnknownParser(f"Неизвестный парсер «{key}». Известные: {known}") from None
```

- [ ] **Step 5: Запустить тесты**

Run: `uv run pytest tests/test_parsers.py -v`
Expected: PASS, 3 теста

- [ ] **Step 6: Коммит**

```bash
git add src/trading/parsers tests/test_parsers.py
git commit -m "Реестр парсеров и парсер quotes"
```

---

### Task 3: JSONL-хранилище

**Files:**
- Create: `src/trading/storage/jsonl.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_storage.py`:

```python
import json

from trading.storage.jsonl import JsonlSink


def test_writes_to_part_file_until_committed(tmp_path):
    sink = JsonlSink(tmp_path, "quotes-daily", 42).open()
    sink.write({"author": "Кафка"})

    part = tmp_path / "quotes-daily" / "42.jsonl.part"
    final = tmp_path / "quotes-daily" / "42.jsonl"
    assert part.exists()
    assert not final.exists()

    locator = sink.commit()

    assert not part.exists()
    assert final.exists()
    assert locator == str(final)


def test_commit_keeps_cyrillic_readable(tmp_path):
    sink = JsonlSink(tmp_path, "quotes-daily", 1).open()
    sink.write({"author": "Кафка", "tags": ["абсурд"]})
    path = sink.commit()

    text = (tmp_path / "quotes-daily" / "1.jsonl").read_text(encoding="utf-8")
    assert "Кафка" in text  # не Ка...
    assert json.loads(text) == {"author": "Кафка", "tags": ["абсурд"]}
    assert path.endswith("1.jsonl")


def test_one_line_per_item(tmp_path):
    sink = JsonlSink(tmp_path, "quotes-daily", 7).open()
    for index in range(3):
        sink.write({"n": index})
    sink.commit()

    lines = (tmp_path / "quotes-daily" / "7.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["n"] for line in lines] == [0, 1, 2]


def test_abandon_keeps_partial_file_and_returns_its_path(tmp_path):
    sink = JsonlSink(tmp_path, "quotes-daily", 9).open()
    sink.write({"author": "Кафка"})

    locator = sink.abandon()

    part = tmp_path / "quotes-daily" / "9.jsonl.part"
    assert part.exists()
    assert locator == str(part)
    assert not (tmp_path / "quotes-daily" / "9.jsonl").exists()


def test_counts_written_items(tmp_path):
    sink = JsonlSink(tmp_path, "quotes-daily", 3).open()
    sink.write({"a": 1})
    sink.write({"a": 2})
    sink.commit()

    assert sink.count == 2
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `uv run pytest tests/test_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading.storage.jsonl'`

- [ ] **Step 3: Написать реализацию**

Создать `src/trading/storage/jsonl.py`:

```python
"""JSONL-файл на запуск: айтем — строка.

Пишем в файл с суффиксом ``.part`` и переименовываем в конце, поэтому имя без
суффикса всегда означает «краул дошёл до конца». Файл, оставшийся как ``.part``,
— это частичные данные упавшего запуска, и терять их незачем.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlSink:
    """Одна папка на источник, один файл на запуск.

    Каталог — по коду источника, а не по имени парсера: один парсер под двумя
    расписаниями не должен смешивать выдачу.
    """

    def __init__(self, root: Path | str, source: str, run_id: int) -> None:
        self.path = Path(root) / source / f"{run_id}.jsonl"
        self.partial = self.path.parent / f"{self.path.name}.part"
        self.count = 0
        self._handle = None

    def open(self) -> JsonlSink:
        self.partial.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.partial.open("w", encoding="utf-8")
        return self

    def write(self, item: Any) -> None:
        json.dump(item, self._handle, ensure_ascii=False)
        self._handle.write("\n")
        self.count += 1

    def commit(self) -> str:
        """Закрыть файл и снять суффикс. Возвращает путь для result_locator."""
        self._close()
        self.partial.replace(self.path)
        return str(self.path)

    def abandon(self) -> str:
        """Закрыть файл, оставив суффикс. Возвращает путь к частичным данным."""
        self._close()
        return str(self.partial)

    def _close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
```

- [ ] **Step 4: Запустить тесты**

Run: `uv run pytest tests/test_storage.py -v`
Expected: PASS, 5 тестов

- [ ] **Step 5: Коммит**

```bash
git add src/trading/storage tests/test_storage.py
git commit -m "JSONL-хранилище: файл на запуск, .part до завершения"
```

---

### Task 4: Буфер логов

**Files:**
- Create: `src/trading/runner/logs.py`
- Test: `tests/test_logs.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_logs.py`:

```python
import logging
import threading

from trading.runner.logs import LogBuffer, LogBufferHandler


def test_drain_returns_entries_and_empties_buffer():
    buffer = LogBuffer()
    buffer.add("INFO", "первая")
    buffer.add("INFO", "вторая")

    batch = buffer.drain()

    assert [entry["message"] for entry in batch] == ["первая", "вторая"]
    assert buffer.drain() == []


def test_entry_has_level_message_and_iso_timestamp_with_timezone():
    buffer = LogBuffer()
    buffer.add("WARNING", "осторожно")

    entry = buffer.drain()[0]

    assert entry["level"] == "WARNING"
    assert entry["message"] == "осторожно"
    assert entry["ts"].endswith("+00:00")


def test_drain_caps_batch_size():
    buffer = LogBuffer(max_batch=2)
    for index in range(5):
        buffer.add("INFO", str(index))

    assert len(buffer.drain()) == 2
    assert len(buffer.drain()) == 2
    assert len(buffer.drain()) == 1
    assert buffer.drain() == []


def test_entries_below_threshold_are_dropped():
    buffer = LogBuffer(min_level="WARNING")
    buffer.add("DEBUG", "шум")
    buffer.add("INFO", "тоже шум")
    buffer.add("WARNING", "важное")
    buffer.add("ERROR", "важное тоже")

    assert [entry["message"] for entry in buffer.drain()] == ["важное", "важное тоже"]


def test_unknown_level_is_treated_as_info():
    buffer = LogBuffer(min_level="INFO")
    buffer.add("ЧТО-ТО", "странное")

    entry = buffer.drain()[0]
    assert entry["level"] == "ЧТО-ТО"  # уровень не подменяем, решает сервер


async def test_log_hook_records_bare_string_as_info():
    """ctx.log отдаёт строку без уровня — такие строки идут как INFO."""
    buffer = LogBuffer()
    await buffer.log("страница 2 из 10")

    entry = buffer.drain()[0]
    assert entry == {"ts": entry["ts"], "level": "INFO", "message": "страница 2 из 10"}


def test_handler_forwards_records_from_logging():
    buffer = LogBuffer()
    logger = logging.getLogger("test_handler_forwards")
    logger.setLevel(logging.DEBUG)
    handler = LogBufferHandler(buffer)
    logger.addHandler(handler)
    try:
        logger.warning("crawl.error %s", "GET /x")
    finally:
        logger.removeHandler(handler)

    entry = buffer.drain()[0]
    assert entry["level"] == "WARNING"
    assert entry["message"] == "crawl.error GET /x"


def test_add_is_thread_safe():
    """logging.Handler зовётся синхронно и может прийти из чужого потока."""
    buffer = LogBuffer(max_batch=10_000)

    def worker():
        for _ in range(200):
            buffer.add("INFO", "x")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(buffer.drain()) == 800
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `uv run pytest tests/test_logs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading.runner.logs'`

- [ ] **Step 3: Написать реализацию**

Создать `src/trading/runner/logs.py`:

```python
"""Буфер строк лога и мост из stdlib logging.

Источников два — хук ``ctx.log`` парсера и логгер ``collector`` самого
фреймворка, — а буфер один, потому что отправляются они одним потоком строк.

Буфер под блокировкой: ``logging.Handler`` вызывается синхронно и может прийти
из чужого потока, а вычерпывает буфер асинхронная задача.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

#: Порог фильтрации. Уровни те же, что у stdlib logging и у control plane.
LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

#: Предел пачки на стороне control plane (CONTROL["MAX_LOG_BATCH"]).
MAX_BATCH = 500


class LogBuffer:
    """Копит строки, отдаёт пачками."""

    def __init__(self, min_level: str = "INFO", max_batch: int = MAX_BATCH) -> None:
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._threshold = LEVELS.get(min_level.upper(), LEVELS["INFO"])
        self._max_batch = max_batch

    def add(self, level: str, message: str, context: dict[str, Any] | None = None) -> None:
        """Записать строку. Уровень ниже порога отбрасывается здесь же."""
        if LEVELS.get(level.upper(), LEVELS["INFO"]) < self._threshold:
            return

        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
        if context:
            entry["context"] = context

        with self._lock:
            self._entries.append(entry)

    async def log(self, message: str) -> None:
        """Хук для ``ctx.log``: голая строка без уровня — это INFO."""
        self.add("INFO", message)

    def drain(self) -> list[dict[str, Any]]:
        """Забрать следующую пачку, не больше ``max_batch`` строк."""
        with self._lock:
            batch = self._entries[: self._max_batch]
            del self._entries[: len(batch)]
        return batch

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


class LogBufferHandler(logging.Handler):
    """Обработчик stdlib logging, складывающий записи в LogBuffer."""

    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.add(record.levelname, record.getMessage())
        except Exception:  # noqa: BLE001 — падение логирования не должно ронять краул
            self.handleError(record)
```

- [ ] **Step 4: Запустить тесты**

Run: `uv run pytest tests/test_logs.py -v`
Expected: PASS, 8 тестов

- [ ] **Step 5: Коммит**

```bash
git add src/trading/runner/logs.py tests/test_logs.py
git commit -m "Буфер логов: пачки, фильтр по уровню, мост из stdlib logging"
```

---

### Task 5: Конфигурация

**Files:**
- Create: `src/trading/runner/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_config.py`:

```python
import pytest

from trading.runner.config import Config, load_env_file


def test_from_env_reads_all_values(monkeypatch):
    monkeypatch.setenv("CONTROL_URL", "http://control:9000")
    monkeypatch.setenv("RUNNER_TOKEN", "секрет")
    monkeypatch.setenv("DATA_DIR", "/tmp/данные")
    monkeypatch.setenv("POLL_INTERVAL", "3")
    monkeypatch.setenv("HTTP_TIMEOUT", "5")
    monkeypatch.setenv("LOG_FLUSH_SECONDS", "0.5")

    config = Config.from_env()

    assert config.control_url == "http://control:9000"
    assert config.token == "секрет"
    assert str(config.data_dir) == "/tmp/данные"
    assert config.poll_interval == 3.0
    assert config.http_timeout == 5.0
    assert config.log_flush_seconds == 0.5


def test_from_env_has_defaults(monkeypatch):
    for name in ("CONTROL_URL", "DATA_DIR", "POLL_INTERVAL", "HTTP_TIMEOUT", "LOG_FLUSH_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RUNNER_TOKEN", "секрет")

    config = Config.from_env()

    assert config.control_url == "http://127.0.0.1:8000"
    assert str(config.data_dir).endswith("data")
    assert config.poll_interval == 10.0
    assert config.http_timeout == 30.0
    assert config.log_flush_seconds == 2.0


def test_missing_token_fails_at_startup(monkeypatch):
    monkeypatch.delenv("RUNNER_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="RUNNER_TOKEN"):
        Config.from_env()


def test_control_url_loses_trailing_slash(monkeypatch):
    monkeypatch.setenv("RUNNER_TOKEN", "секрет")
    monkeypatch.setenv("CONTROL_URL", "http://control:9000/")

    assert Config.from_env().control_url == "http://control:9000"


def test_load_env_file_does_not_override_environment(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text('RUNNER_TOKEN="из файла"\n# комментарий\nDATA_DIR=из-файла\n', encoding="utf-8")
    monkeypatch.setenv("RUNNER_TOKEN", "из окружения")
    monkeypatch.delenv("DATA_DIR", raising=False)

    load_env_file(env)

    import os

    assert os.environ["RUNNER_TOKEN"] == "из окружения"
    assert os.environ["DATA_DIR"] == "из-файла"


def test_load_env_file_tolerates_missing_file(tmp_path):
    load_env_file(tmp_path / "нет-такого")  # не бросает
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading.runner.config'`

- [ ] **Step 3: Написать реализацию**

Создать `src/trading/runner/config.py`:

```python
"""Настройки раннера из окружения. Локально — из .env в корне репозитория.

Читалка .env повторяет ту, что в dashboard: без внешних зависимостей и с тем же
правилом приоритета, чтобы два репозитория рядом вели себя одинаково.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: src/trading/runner/config.py -> корень репозитория
ROOT_DIR = Path(__file__).resolve().parents[3]


def load_env_file(path: Path | None = None) -> None:
    """Читает .env в окружение процесса.

    Переменные, уже заданные в окружении, имеют приоритет над файлом — так
    настройки из CI или docker не перетираются локальным .env. Формат простой:
    KEY=value, строки с # игнорируются, кавычки снимаются.
    """
    path = path or ROOT_DIR / ".env"
    if not path.exists():
        return

    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value  # при дубле ключа побеждает последняя строка

    for key, value in values.items():
        os.environ.setdefault(key, value)


@dataclass(frozen=True, slots=True)
class Config:
    control_url: str
    token: str
    data_dir: Path
    poll_interval: float
    http_timeout: float
    log_flush_seconds: float

    @classmethod
    def from_env(cls) -> Config:
        """Собрать настройки. Без токена раннеру делать нечего — падаем сразу."""
        token = os.environ.get("RUNNER_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "Не задан RUNNER_TOKEN. Создайте раннера в админке "
                "(Парсеры -> Раннеры) и положите его токен в .env"
            )

        return cls(
            control_url=os.environ.get("CONTROL_URL", "http://127.0.0.1:8000").rstrip("/"),
            token=token,
            data_dir=Path(os.environ.get("DATA_DIR") or ROOT_DIR / "data"),
            poll_interval=float(os.environ.get("POLL_INTERVAL", "10")),
            http_timeout=float(os.environ.get("HTTP_TIMEOUT", "30")),
            log_flush_seconds=float(os.environ.get("LOG_FLUSH_SECONDS", "2")),
        )
```

- [ ] **Step 4: Запустить тесты**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS, 6 тестов

- [ ] **Step 5: Коммит**

```bash
git add src/trading/runner/config.py tests/test_config.py
git commit -m "Настройки раннера из окружения и .env"
```

---

### Task 6: Клиент control plane

**Files:**
- Create: `src/trading/control/client.py`
- Test: `tests/test_control_client.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_control_client.py`:

```python
import httpx
import pytest

from trading.control.client import ControlClient


def build_client(handler):
    """Клиент поверх MockTransport: control plane изображается функцией."""
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://control",
        headers={"X-Runner-Token": "секрет"},
    )
    return ControlClient(http)


async def test_claim_returns_job_and_poll_interval():
    def handler(request):
        assert request.url.path == "/api/v1/runs/claim/"
        assert request.method == "POST"
        assert request.headers["X-Runner-Token"] == "секрет"
        return httpx.Response(200, json={"run": {"id": 7, "parser": "quotes"}, "poll_interval": 3})

    job, poll = await build_client(handler).claim()

    assert job == {"id": 7, "parser": "quotes"}
    assert poll == 3.0


async def test_claim_returns_none_when_there_is_no_work():
    def handler(request):
        return httpx.Response(200, json={"run": None, "poll_interval": 10})

    job, poll = await build_client(handler).claim()

    assert job is None
    assert poll == 10.0


async def test_claim_raises_on_bad_token():
    def handler(request):
        return httpx.Response(401, json={"detail": "Нужен валидный X-Runner-Token"})

    with pytest.raises(httpx.HTTPStatusError):
        await build_client(handler).claim()


async def test_send_logs_posts_entries_and_returns_accepted():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx.Response(200, json={"accepted": 2})

    entries = [{"ts": "2026-09-18T10:00:00+00:00", "level": "INFO", "message": "раз"}]
    accepted = await build_client(handler).send_logs(7, entries)

    assert accepted == 2
    assert seen["path"] == "/api/v1/runs/7/logs/"
    assert b'"entries"' in seen["body"]


async def test_heartbeat_hits_the_right_path():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json={"lease_expires_at": "2026-09-18T10:10:00+00:00"})

    await build_client(handler).heartbeat(7)

    assert seen["path"] == "/api/v1/runs/7/heartbeat/"


async def test_complete_sends_status_counters_and_locator():
    seen = {}

    def handler(request):
        import json

        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 7, "status": "success", "source_active": True})

    result = await build_client(handler).complete(
        7,
        status="success",
        counters={"items_total": 100, "reason": "done"},
        result_locator="/data/quotes/7.jsonl",
        error="",
    )

    assert seen["path"] == "/api/v1/runs/7/complete/"
    assert seen["payload"]["status"] == "success"
    assert seen["payload"]["counters"]["items_total"] == 100
    assert seen["payload"]["result_locator"] == "/data/quotes/7.jsonl"
    assert result["status"] == "success"


async def test_open_builds_client_with_token_header():
    client = ControlClient.open("http://control:9000", "секрет", timeout=5.0)
    try:
        assert client.http.headers["X-Runner-Token"] == "секрет"
        assert str(client.http.base_url) == "http://control:9000"
    finally:
        await client.aclose()
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `uv run pytest tests/test_control_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading.control.client'`

- [ ] **Step 3: Написать реализацию**

Создать `src/trading/control/client.py`:

```python
"""HTTP-клиент control plane: четыре эндпоинта и ничего больше.

Клиент принимает готовый ``httpx.AsyncClient``, а не собирает его сам, — так
тест подставляет ``MockTransport`` и весь цикл проверяется без сети. Обычный
вызов идёт через ``ControlClient.open()``.

Асинхронный, потому что heartbeat обязан идти во время краула, а шов ``ctx.log``
у фреймворка тоже async.
"""

from __future__ import annotations

from typing import Any

import httpx

TOKEN_HEADER = "X-Runner-Token"


class ControlClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    @classmethod
    def open(cls, base_url: str, token: str, timeout: float = 30.0) -> ControlClient:
        return cls(
            httpx.AsyncClient(
                base_url=base_url.rstrip("/"),
                timeout=timeout,
                headers={TOKEN_HEADER: token},
            )
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    async def claim(self) -> tuple[dict[str, Any] | None, float]:
        """Забрать задание. ``None`` в первом элементе — работы нет."""
        response = await self.http.post("/api/v1/runs/claim/")
        response.raise_for_status()
        payload = response.json()
        return payload.get("run"), float(payload.get("poll_interval") or 10)

    async def send_logs(self, run_id: int, entries: list[dict[str, Any]]) -> int:
        """Отправить пачку строк. Продлевает аренду — это делает сервер."""
        response = await self.http.post(f"/api/v1/runs/{run_id}/logs/", json={"entries": entries})
        response.raise_for_status()
        return int(response.json().get("accepted", 0))

    async def heartbeat(self, run_id: int) -> None:
        response = await self.http.post(f"/api/v1/runs/{run_id}/heartbeat/")
        response.raise_for_status()

    async def complete(
        self,
        run_id: int,
        *,
        status: str,
        counters: dict[str, Any],
        result_locator: str = "",
        error: str = "",
    ) -> dict[str, Any]:
        response = await self.http.post(
            f"/api/v1/runs/{run_id}/complete/",
            json={
                "status": status,
                "counters": counters,
                "result_locator": result_locator,
                "error": error,
            },
        )
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Запустить тесты**

Run: `uv run pytest tests/test_control_client.py -v`
Expected: PASS, 7 тестов

- [ ] **Step 5: Коммит**

```bash
git add src/trading/control tests/test_control_client.py
git commit -m "Клиент control plane: claim, logs, heartbeat, complete"
```

---

### Task 7: Приведение params и счётчики

Две чистые функции, которые дальше понадобятся `execute_run()`. Отдельной задачей, потому что тестируются без всякой асинхронщины.

**Files:**
- Create: `src/trading/runner/execute.py`
- Test: `tests/test_execute_helpers.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_execute_helpers.py`:

```python
from collector import Stats

from trading.runner.execute import coerce_params, counters_from


def test_numbers_become_strings():
    assert coerce_params({"concurrency": 2, "delay": 0.5}) == {"concurrency": "2", "delay": "0.5"}


def test_booleans_become_lowercase_words():
    """bool — подкласс int, и без отдельной ветки True превратится в «1»."""
    assert coerce_params({"debug": True, "dry": False}) == {"debug": "true", "dry": "false"}


def test_strings_pass_through():
    assert coerce_params({"region": "Москва"}) == {"region": "Москва"}


def test_nested_structures_pass_through_untouched():
    """Списки и словари читает сам парсер через ctx.params, фреймворк в них не лезет."""
    params = {"regions": ["77", "50"], "filters": {"min": 1}, "since": None}
    assert coerce_params(params) == params


def test_empty_and_none_give_empty_dict():
    assert coerce_params(None) == {}
    assert coerce_params({}) == {}


def test_counters_map_stats_onto_control_plane_fields():
    stats = Stats(requests=12, errors=1, items=100, started_at=0.0, finished_at=2.5, reason="done")

    counters = counters_from(stats)

    assert counters["items_total"] == 100
    assert counters["items_new"] == 0
    assert counters["items_updated"] == 0
    assert counters["requests"] == 12
    assert counters["errors"] == 1
    assert counters["elapsed"] == 2.5
    assert counters["reason"] == "done"


def test_counters_from_none_are_empty():
    """Краул мог не начаться: неизвестный парсер, падение на старте."""
    assert counters_from(None) == {}
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `uv run pytest tests/test_execute_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading.runner.execute'`

- [ ] **Step 3: Написать реализацию**

Создать `src/trading/runner/execute.py` (пока только две функции, остальное добавит Task 8):

```python
"""Выполнение одного задания: от claim до complete."""

from __future__ import annotations

from typing import Any

from collector import Stats


def coerce_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Привести params из админки к тому, что ждёт фреймворк.

    В админке params — произвольный JSON, и человек напишет ``{"concurrency": 2}``
    числом. Фреймворк читает свои знобы как строки, и без приведения
    ``read_concurrency`` молча свалится в дефолт, написав ``params.bad_concurrency``
    в лог — отлаживать такое неприятно.

    Вложенные структуры отдаём как есть: их читает сам парсер через ``ctx.params``,
    фреймворк в них не заглядывает.
    """
    result: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if isinstance(value, bool):
            # Проверка раньше int: bool — его подкласс, иначе True станет «1»
            result[key] = "true" if value else "false"
        elif isinstance(value, (int, float, str)):
            result[key] = str(value)
        else:
            result[key] = value
    return result


def counters_from(stats: Stats | None) -> dict[str, Any]:
    """Счётчики краула в том виде, в каком их понимает control plane.

    ``items_new`` и ``items_updated`` — нули осознанно: JSONL не дедуплицирует,
    врать нечем. Остальное сервер сложит в свободное поле ``counters``.
    """
    if stats is None:
        return {}

    return {
        "items_total": stats.items,
        "items_new": 0,
        "items_updated": 0,
        "requests": stats.requests,
        "errors": stats.errors,
        "elapsed": round(stats.elapsed, 3),
        "reason": stats.reason,
    }
```

- [ ] **Step 4: Запустить тесты**

Run: `uv run pytest tests/test_execute_helpers.py -v`
Expected: PASS, 7 тестов

- [ ] **Step 5: Коммит**

```bash
git add src/trading/runner/execute.py tests/test_execute_helpers.py
git commit -m "Приведение params и маппинг счётчиков краула"
```

---

### Task 8: Выполнение задания целиком

Самая содержательная задача. Тест интеграционный и без сети: краул ходит на локальный `http.server`, control plane изображает `MockTransport`.

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/fixtures/page1.html`, `tests/fixtures/page2.html`
- Modify: `src/trading/runner/execute.py`
- Modify: `src/trading/parsers/__init__.py`
- Test: `tests/test_execute.py`

- [ ] **Step 1: Создать фикстуры страниц**

`tests/fixtures/page1.html`:

```html
<!doctype html>
<html><body>
  <div class="quote">
    <span class="text">Цитата раз</span>
    <small class="author">Кафка</small>
    <div class="tags"><a class="tag">абсурд</a></div>
  </div>
  <div class="quote">
    <span class="text">Цитата два</span>
    <small class="author">Борхес</small>
    <div class="tags"><a class="tag">лабиринт</a></div>
  </div>
  <ul><li class="next"><a href="/page2.html">Дальше</a></li></ul>
</body></html>
```

`tests/fixtures/page2.html`:

```html
<!doctype html>
<html><body>
  <div class="quote">
    <span class="text">Цитата три</span>
    <small class="author">Кальвино</small>
    <div class="tags"><a class="tag">города</a></div>
  </div>
</body></html>
```

- [ ] **Step 2: Написать conftest с локальным сайтом**

Создать `tests/conftest.py`:

```python
"""Общие фикстуры. Сети в тестах нет: сайт поднимается локально.

Перехватить запросы краула нельзя — фреймворк ходит через curl_cffi, мимо
httpx-транспортов. Поэтому поднимаем настоящий http.server на случайном порту
и отдаём фикстуры с диска.
"""

import functools
import http.server
import threading
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # без шума в выводе тестов
        pass


@pytest.fixture
def local_site():
    """Адрес локального сайта с фикстурами, например http://127.0.0.1:54321."""
    handler = functools.partial(QuietHandler, directory=str(FIXTURES))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
```

- [ ] **Step 3: Написать падающий тест**

Создать `tests/test_execute.py`:

```python
import json
from typing import Any

import httpx
import pytest
from collector import Parser, Response, Settings

from trading.control.client import ControlClient
from trading.parsers import REGISTRY
from trading.runner.execute import execute_run


class FakeControlPlane:
    """Считает вызовы и складывает то, что прислал раннер."""

    def __init__(self):
        self.log_entries: list[dict[str, Any]] = []
        self.heartbeats = 0
        self.completion: dict[str, Any] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/logs/"):
            self.log_entries.extend(json.loads(request.content)["entries"])
            return httpx.Response(200, json={"accepted": 1})
        if path.endswith("/heartbeat/"):
            self.heartbeats += 1
            return httpx.Response(200, json={"lease_expires_at": "2026-09-18T10:10:00+00:00"})
        if path.endswith("/complete/"):
            self.completion = json.loads(request.content)
            return httpx.Response(200, json={"id": 1, "status": self.completion["status"], "source_active": True})
        raise AssertionError(f"неожиданный запрос: {path}")

    def client(self) -> ControlClient:
        return ControlClient(
            httpx.AsyncClient(transport=httpx.MockTransport(self.handler), base_url="http://control")
        )


def job(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 1,
        "source": "тест",
        "parser": "quotes-local",
        "params": {},
        "log_level": "DEBUG",
        "trigger": "manual",
        "lease_expires_at": "2026-09-18T10:10:00+00:00",
    }
    return base | overrides


@pytest.fixture
def local_quotes(local_site, monkeypatch):
    """Парсер quotes, нацеленный на локальный сайт, временно в реестре."""

    class LocalQuotes(Parser):
        name = "quotes-local"
        start_urls = [f"{local_site}/page1.html"]
        settings = Settings(impersonate=None)

        async def parse(self, response: Response) -> Any:
            page = response.selector()
            await self.log(f"разбираю {response.request.url}")
            for quote in page.css("div.quote"):
                yield {
                    "text": quote.css("span.text::text").get(),
                    "author": quote.css("small.author::text").get(),
                    "tags": quote.css("div.tags a.tag::text").getall(),
                }
            next_page = page.css("li.next a::attr(href)").get()
            if next_page:
                yield response.follow(next_page)

    monkeypatch.setitem(REGISTRY, "quotes-local", LocalQuotes)
    return LocalQuotes


async def test_successful_run_writes_items_and_reports_counters(local_quotes, tmp_path):
    control = FakeControlPlane()
    client = control.client()
    try:
        await execute_run(client, job(), data_dir=tmp_path, log_flush_seconds=0.05)
    finally:
        await client.aclose()

    assert control.completion["status"] == "success"
    assert control.completion["counters"]["items_total"] == 3
    assert control.completion["counters"]["requests"] == 2
    assert control.completion["counters"]["reason"] == "done"

    path = tmp_path / "тест" / "1.jsonl"
    assert control.completion["result_locator"] == str(path)
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [item["author"] for item in items] == ["Кафка", "Борхес", "Кальвино"]


async def test_parser_log_lines_reach_control_plane(local_quotes, tmp_path):
    control = FakeControlPlane()
    client = control.client()
    try:
        await execute_run(client, job(), data_dir=tmp_path, log_flush_seconds=0.05)
    finally:
        await client.aclose()

    messages = [entry["message"] for entry in control.log_entries]
    assert any("разбираю" in message for message in messages)
    assert all(entry["level"] in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} for entry in control.log_entries)


async def test_unknown_parser_fails_the_run_with_a_readable_error(tmp_path):
    control = FakeControlPlane()
    client = control.client()
    try:
        await execute_run(client, job(parser="нет-такого"), data_dir=tmp_path)
    finally:
        await client.aclose()

    assert control.completion["status"] == "failed"
    assert "нет-такого" in control.completion["error"]
    assert control.completion["result_locator"] == ""
    assert not list(tmp_path.iterdir())  # файла не завели


async def test_failing_crawl_still_reports_partial_data(local_site, monkeypatch, tmp_path):
    """Одна упавшая страница роняет краул, но записанное до неё сохраняется."""

    class HalfBroken(Parser):
        name = "half-broken"
        start_urls = [f"{local_site}/page1.html"]
        settings = Settings(impersonate=None)

        async def parse(self, response: Response) -> Any:
            page = response.selector()
            for quote in page.css("div.quote"):
                yield {"author": quote.css("small.author::text").get()}
            yield response.follow("/нет-такой-страницы.html")

    monkeypatch.setitem(REGISTRY, "half-broken", HalfBroken)

    control = FakeControlPlane()
    client = control.client()
    try:
        await execute_run(client, job(parser="half-broken"), data_dir=tmp_path, log_flush_seconds=0.05)
    finally:
        await client.aclose()

    assert control.completion["status"] == "failed"
    assert control.completion["error"]
    part = tmp_path / "тест" / "1.jsonl.part"
    assert control.completion["result_locator"] == str(part)
    assert part.exists()
    lines = part.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # обе цитаты с первой страницы на месте


async def test_max_requests_ends_successfully_with_a_warning(local_quotes, tmp_path):
    control = FakeControlPlane()
    client = control.client()
    try:
        await execute_run(
            client,
            job(params={"max_requests": 1}),
            data_dir=tmp_path,
            log_flush_seconds=0.05,
        )
    finally:
        await client.aclose()

    assert control.completion["status"] == "success"
    assert control.completion["counters"]["reason"] == "max_requests"
    assert control.completion["counters"]["items_total"] == 2  # только первая страница
    warnings = [entry for entry in control.log_entries if entry["level"] == "WARNING"]
    assert any("max_requests" in entry["message"] for entry in warnings)


async def test_stop_flag_finishes_the_run_as_failed(local_quotes, tmp_path):
    """Мягкая остановка: break из stream() даёт reason='cancelled'."""
    import threading

    stop = threading.Event()
    stop.set()

    control = FakeControlPlane()
    client = control.client()
    try:
        await execute_run(client, job(), data_dir=tmp_path, log_flush_seconds=0.05, stop=stop)
    finally:
        await client.aclose()

    assert control.completion["status"] == "failed"
    assert "Прерван оператором" in control.completion["error"]
```

Заметьте `params={"max_requests": 1}` числом — это и есть проверка `coerce_params` на живом краулe. И `Settings(impersonate=None)` в тестовых парсерах: отпечаток браузера против `http.server` не нужен.

- [ ] **Step 4: Запустить тест и убедиться, что он падает**

Run: `uv run pytest tests/test_execute.py -v`
Expected: FAIL — `ImportError: cannot import name 'execute_run' from 'trading.runner.execute'`

- [ ] **Step 5: Дописать `execute.py`**

Добавить импорты в начало файла (после `from __future__ import annotations`):

```python
import asyncio
import contextlib
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collector import Stats, open_crawler

from trading.control.client import ControlClient
from trading.parsers import UnknownParser, resolve
from trading.runner.logs import LogBuffer, LogBufferHandler
from trading.storage.jsonl import JsonlSink
```

Строку `from collector import Stats` из Task 7 заменить на эту, объединённую.

Добавить в конец файла:

```python
async def execute_run(
    client: ControlClient,
    job: dict[str, Any],
    *,
    data_dir: Path | str,
    log_flush_seconds: float = 2.0,
    stop: threading.Event | None = None,
) -> None:
    """Выполнить одно задание и закрыть его в control plane.

    Наружу не бросает: любой исход задания — это ``complete`` со статусом,
    а не исключение в цикле опроса.
    """
    run_id = job["id"]
    buffer = LogBuffer(min_level=job.get("log_level") or "INFO")

    try:
        parser_cls = resolve(job["parser"])
    except UnknownParser as exc:
        buffer.add("ERROR", str(exc))
        await _flush(client, run_id, buffer)
        await client.complete(run_id, status="failed", counters={}, error=str(exc))
        return

    sink = JsonlSink(data_dir, job["source"], run_id).open()
    handler = LogBufferHandler(buffer)
    framework_logger = logging.getLogger("collector")
    framework_logger.addHandler(handler)
    previous_level = framework_logger.level
    framework_logger.setLevel(logging.DEBUG)

    shipper = asyncio.create_task(_ship_logs(client, run_id, buffer, log_flush_seconds))
    heartbeat = asyncio.create_task(_heartbeat(client, run_id, job.get("lease_expires_at")))

    status, error, stats = "success", "", None
    try:
        async with open_crawler(
            parser_cls,
            params=coerce_params(job.get("params")),
            log=buffer.log,
        ) as crawler:
            async for item in crawler.stream():
                sink.write(item)
                if stop is not None and stop.is_set():
                    # Штатный путь фреймворка: break останавливает краул,
                    # stats.reason становится 'cancelled'.
                    break
            stats = crawler.stats
            if stop is not None and stop.is_set():
                status, error = "failed", "Прерван оператором"
    except Exception as exc:  # noqa: BLE001 — исход задания, а не падение раннера
        status = "failed"
        failed_crawler = getattr(exc, "crawler", None)
        stats = failed_crawler.stats if failed_crawler is not None else None
        error = f"{type(exc).__name__}: {exc}"
        if failed_crawler is not None and len(failed_crawler.errors) > 1:
            error += f" (запросов с ошибкой: {len(failed_crawler.errors)})"
    finally:
        for task in (shipper, heartbeat):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        framework_logger.removeHandler(handler)
        framework_logger.setLevel(previous_level)

    locator = sink.commit() if status == "success" else sink.abandon()

    if stats is not None and stats.reason == "max_requests":
        buffer.add("WARNING", "Достигнут предел max_requests — данные могут быть неполными")

    await _flush(client, run_id, buffer)
    await _complete_with_retries(
        client,
        run_id,
        status=status,
        counters=counters_from(stats),
        result_locator=locator,
        error=error,
    )


async def _ship_logs(
    client: ControlClient, run_id: int, buffer: LogBuffer, flush_seconds: float
) -> None:
    """Периодически отдавать накопленное, пока идёт краул."""
    while True:
        await asyncio.sleep(flush_seconds)
        await _flush(client, run_id, buffer)


async def _flush(client: ControlClient, run_id: int, buffer: LogBuffer) -> None:
    """Вычерпать буфер пачками. Неудачная отправка теряется: логи не важнее данных."""
    while batch := buffer.drain():
        try:
            await client.send_logs(run_id, batch)
        except Exception:  # noqa: BLE001
            return


async def _heartbeat(client: ControlClient, run_id: int, lease_expires_at: str | None) -> None:
    """Продлевать аренду втрое чаще, чем она истекает."""
    interval = _heartbeat_interval(lease_expires_at)
    while True:
        await asyncio.sleep(interval)
        with contextlib.suppress(Exception):
            await client.heartbeat(run_id)


def _heartbeat_interval(lease_expires_at: str | None, floor: float = 5.0) -> float:
    """Треть оставшейся аренды, но не чаще, чем раз в ``floor`` секунд."""
    if not lease_expires_at:
        return 60.0
    try:
        expires = datetime.fromisoformat(lease_expires_at)
    except ValueError:
        return 60.0
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    remaining = (expires - datetime.now(timezone.utc)).total_seconds()
    return max(remaining / 3, floor)


async def _complete_with_retries(
    client: ControlClient,
    run_id: int,
    *,
    status: str,
    counters: dict[str, Any],
    result_locator: str,
    error: str,
    attempts: int = 3,
) -> None:
    """Закрыть запуск. Если control plane молчит — сдаёмся, задание протухнет по аренде."""
    for attempt in range(1, attempts + 1):
        try:
            await client.complete(
                run_id,
                status=status,
                counters=counters,
                result_locator=result_locator,
                error=error,
            )
            return
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts:
                logging.getLogger(__name__).error(
                    "не удалось закрыть запуск %s: %r — он протухнет по аренде", run_id, exc
                )
                return
            await asyncio.sleep(2**attempt)
```

- [ ] **Step 6: Запустить тесты**

Run: `uv run pytest tests/test_execute.py -v`
Expected: PASS, 6 тестов

- [ ] **Step 7: Прогнать всё и линтер**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: все тесты PASS, ruff без замечаний

- [ ] **Step 8: Коммит**

```bash
git add src/trading/runner/execute.py tests/conftest.py tests/fixtures tests/test_execute.py
git commit -m "Выполнение задания: краул, запись айтемов, логи, heartbeat, complete"
```

---

### Task 9: Цикл опроса и точка входа

**Files:**
- Create: `src/trading/runner/loop.py`
- Create: `src/trading/runner/__main__.py`
- Test: `tests/test_loop.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_loop.py`:

```python
import threading
from pathlib import Path

import httpx
import pytest

from trading.control.client import ControlClient
from trading.runner.config import Config
from trading.runner.loop import poll_once


def config(tmp_path: Path) -> Config:
    return Config(
        control_url="http://control",
        token="секрет",
        data_dir=tmp_path,
        poll_interval=0.01,
        http_timeout=5.0,
        log_flush_seconds=0.05,
    )


def client_for(handler) -> ControlClient:
    return ControlClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://control")
    )


async def test_poll_once_without_work_returns_the_servers_interval(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"run": None, "poll_interval": 7})

    client = client_for(handler)
    try:
        assert await poll_once(client, config(tmp_path)) == 7.0
    finally:
        await client.aclose()


async def test_poll_once_survives_an_unreachable_control_plane(tmp_path, capsys):
    def handler(request):
        raise httpx.ConnectError("соединение отклонено")

    client = client_for(handler)
    try:
        delay = await poll_once(client, config(tmp_path))
    finally:
        await client.aclose()

    assert delay == 0.01  # запасной интервал из настроек
    assert "control plane" in capsys.readouterr().err


async def test_poll_once_runs_a_claimed_job_and_returns_no_delay(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        if request.url.path.endswith("/claim/"):
            return httpx.Response(
                200,
                json={
                    "run": {
                        "id": 5,
                        "source": "тест",
                        "parser": "quotes",
                        "params": {},
                        "log_level": "INFO",
                        "trigger": "manual",
                        "lease_expires_at": "2026-09-18T10:10:00+00:00",
                    },
                    "poll_interval": 7,
                },
            )
        raise AssertionError("цикл не должен ходить дальше claim в этом тесте")

    async def fake_execute(client, job, **kwargs):
        calls.append(job["id"])

    monkeypatch.setattr("trading.runner.loop.execute_run", fake_execute)

    client = client_for(handler)
    try:
        delay = await poll_once(client, config(tmp_path))
    finally:
        await client.aclose()

    assert calls == [5]
    assert delay == 0.0  # задание было — за следующим идём сразу


async def test_stop_event_is_passed_to_execution(tmp_path, monkeypatch):
    seen = {}

    def handler(request):
        return httpx.Response(
            200,
            json={
                "run": {
                    "id": 5,
                    "source": "тест",
                    "parser": "quotes",
                    "params": {},
                    "log_level": "INFO",
                    "trigger": "manual",
                    "lease_expires_at": "2026-09-18T10:10:00+00:00",
                },
                "poll_interval": 7,
            },
        )

    async def fake_execute(client, job, **kwargs):
        seen["stop"] = kwargs.get("stop")

    monkeypatch.setattr("trading.runner.loop.execute_run", fake_execute)

    stop = threading.Event()
    client = client_for(handler)
    try:
        await poll_once(client, config(tmp_path), stop=stop)
    finally:
        await client.aclose()

    assert seen["stop"] is stop
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `uv run pytest tests/test_loop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading.runner.loop'`

- [ ] **Step 3: Написать реализацию**

Создать `src/trading/runner/loop.py`:

```python
"""Цикл опроса: забрать задание, выполнить, повторить.

Один раннер выполняет одно задание за раз. Параллелизм внутри краула даёт
``Settings.concurrency``; параллелизм по источникам — это второй запущенный
раннер со своим токеном.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import threading

from trading.control.client import ControlClient
from trading.runner.config import Config
from trading.runner.execute import execute_run


async def poll_once(
    client: ControlClient, config: Config, stop: threading.Event | None = None
) -> float:
    """Один заход за заданием. Возвращает, сколько ждать до следующего.

    Ноль означает «задание было, иди за следующим сразу»: очередь могла
    накопиться, и спать, когда работа есть, незачем.
    """
    try:
        job, poll_interval = await client.claim()
    except Exception as exc:  # noqa: BLE001 — недоступный сервер не должен ронять цикл
        print(f"control plane недоступен: {exc!r}", file=sys.stderr)
        return config.poll_interval

    if job is None:
        return poll_interval

    await execute_run(
        client,
        job,
        data_dir=config.data_dir,
        log_flush_seconds=config.log_flush_seconds,
        stop=stop,
    )
    return 0.0


async def run_forever(config: Config, stop: threading.Event | None = None) -> None:
    """Опрашивать control plane, пока не попросят остановиться."""
    client = ControlClient.open(config.control_url, config.token, timeout=config.http_timeout)
    print(f"Раннер начал опрос {config.control_url}", file=sys.stderr)
    try:
        while stop is None or not stop.is_set():
            delay = await poll_once(client, config, stop=stop)
            if delay:
                await asyncio.sleep(delay)
    finally:
        await client.aclose()


def install_signal_handler(stop: threading.Event) -> None:
    """Ctrl+C просит остановиться, а не убивает.

    Через флаг, а не через ``loop.add_signal_handler``: последний на Windows
    не реализован, а разработка идёт в том числе там. Флаг проверяется в цикле
    по айтемам, поэтому остановка случится после ближайшего айтема — второй
    Ctrl+C прервёт процесс жёстко, и запуск протухнет по аренде.
    """

    def handler(signum, frame):  # noqa: ARG001
        if stop.is_set():
            raise KeyboardInterrupt
        stop.set()
        print("Останавливаюсь после текущего запуска, ещё раз Ctrl+C — жёстко", file=sys.stderr)

    signal.signal(signal.SIGINT, handler)
```

Создать `src/trading/runner/__main__.py`:

```python
"""Точка входа: python -m trading.runner"""

from __future__ import annotations

import asyncio
import sys
import threading

from trading.runner.config import Config, load_env_file
from trading.runner.loop import install_signal_handler, run_forever


def main() -> int:
    load_env_file()
    try:
        config = Config.from_env()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2

    stop = threading.Event()
    install_signal_handler(stop)

    try:
        asyncio.run(run_forever(config, stop))
    except KeyboardInterrupt:
        print("Прервано", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Запустить тесты**

Run: `uv run pytest tests/test_loop.py -v`
Expected: PASS, 4 теста

- [ ] **Step 5: Проверить, что точка входа отвечает на отсутствие токена**

Run: `RUNNER_TOKEN= uv run python -m trading.runner; echo "код возврата: $?"`
Expected: сообщение про `RUNNER_TOKEN` и админку, код возврата 2

- [ ] **Step 6: Прогнать всё**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: все тесты PASS, ruff без замечаний

- [ ] **Step 7: Коммит**

```bash
git add src/trading/runner/loop.py src/trading/runner/__main__.py tests/test_loop.py
git commit -m "Цикл опроса, мягкая остановка по Ctrl+C и точка входа"
```

---

### Task 10: README и сквозная проверка вручную

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-18-runner-collector-integration-design.md`

- [ ] **Step 1: Поправить спеку**

В таблице «Отказы» строка про `cancelled` утверждает, что этот исход не возникает. После Task 9 он возникает — это и есть путь мягкой остановки. Заменить строку

```
| `stats.reason == 'cancelled'` | не возникает: раннер дочитывает `stream()` до конца |
```

на

```
| `stats.reason == 'cancelled'` | мягкая остановка по Ctrl+C: `break` из `stream()`; запуск закрывается как `failed` с текстом «Прерван оператором» |
```

- [ ] **Step 2: Написать README**

Заменить содержимое `README.md`:

````markdown
# trading_platform

Раннер парсеров: забирает задания у [control plane](../dashboard), исполняет их
парсерами на [collector-framework](https://github.com/barabacker/collector-framework)
и складывает результат в JSONL.

Control plane знает, **что и когда** запускать. Этот репозиторий знает, **как**.
Данные через control plane не ходят — только задания, счётчики и логи.

## Стек

| | |
|---|---|
| Python | 3.11+ |
| Краулинг | collector-framework |
| HTTP к control plane | httpx |
| Пакеты и venv | [uv](https://docs.astral.sh/uv/) |
| Тесты | pytest |

## Запуск

```bash
make install
cp .env.example .env    # и вписать RUNNER_TOKEN из админки
make run
```

Токен берётся в админке control plane: Парсеры → Раннеры → создать.

## Структура

```
src/trading/parsers/     парсеры и реестр: ключ из админки -> класс
src/trading/storage/     куда складывать айтемы
src/trading/control/     HTTP-клиент control plane
src/trading/runner/      цикл опроса и выполнение задания
tests/                   тесты; сеть не используется
```

## Как добавить парсер

1. Положить класс в `src/trading/parsers/<имя>.py` — обычный `Parser` из
   документации фреймворка. `process_item()` переопределять не нужно: айтемы
   вычерпывает раннер и пишет в JSONL сам.
2. Дописать строку в `REGISTRY` в `src/trading/parsers/__init__.py`.
3. Завести источник в админке с этим ключом.

Ключ реестра — контракт с админкой, а не путь в Python: класс можно
переименовать, не трогая чужую базу.

**Новый класс или новый источник?** Меняется *как парсить* (селекторы, обход,
`start_urls`) — новый класс. Меняется *насколько напористо* (`concurrency`,
`max_requests`) — тот же класс, другой источник с другими параметрами.

## Данные

`data/<код источника>/<id запуска>.jsonl`, одна строка на айтем.

Файл с суффиксом `.part` — запуск не дошёл до конца; частичные данные
сохраняются намеренно. Путь уходит в поле «результат» у запуска в админке.

## Команды

`make help` покажет список. Основное: `make run`, `make test`, `make lint`,
`make fmt`, `make ci`.

## Настройки

| Переменная | По умолчанию |
|---|---|
| `CONTROL_URL` | `http://127.0.0.1:8000` |
| `RUNNER_TOKEN` | обязательна |
| `DATA_DIR` | `data` |
| `POLL_INTERVAL` | `10` |
| `HTTP_TIMEOUT` | `30` |
| `LOG_FLUSH_SECONDS` | `2` |

## Остановка

Ctrl+C останавливает после текущего айтема: запуск закрывается как «Ошибка»
с текстом «Прерван оператором», частичные данные остаются в `.part`. Второй
Ctrl+C прерывает жёстко — тогда запуск протухнет по аренде на стороне
control plane.
````

- [ ] **Step 3: Поднять control plane**

В соседнем каталоге:

```bash
cd ../dashboard && make run
```

Админка: http://127.0.0.1:8000/admin/

- [ ] **Step 4: Завести раннера и источник в админке**

1. Парсеры → Раннеры → создать, имя любое, скопировать токен.
2. Парсеры → Источники → создать: название «Цитаты», код `quotes`,
   парсер `quotes`, расписание `*/5 * * * *`, параметры `{}`, уровень логов `INFO`.

- [ ] **Step 5: Запустить раннера**

Вписать токен в `.env`, затем:

```bash
make run
```

Expected в stderr: `Раннер начал опрос http://127.0.0.1:8000`

- [ ] **Step 6: Проверить сквозной путь**

В админке нажать у источника «Запустить сейчас», открыть страницу запуска.

Expected:
- запуск появляется со статусом «Выполняется», лента лога наполняется сама;
- по завершении статус «Успех», «получено» — 100 (десять страниц по десять цитат);
- «результат» указывает на `data/quotes/<id>.jsonl`;
- в свободных счётчиках видно `requests`, `errors`, `elapsed`, `reason: done`;
- файл существует, `wc -l` даёт 100, кириллица в нём читается глазами.

```bash
wc -l data/quotes/*.jsonl
head -1 data/quotes/*.jsonl
```

- [ ] **Step 7: Проверить путь отказа**

Поменять у источника парсер на `нет-такого`, нажать «Запустить сейчас».

Expected: статус «Ошибка», в поле «ошибка» — `Неизвестный парсер «нет-такого». Известные: quotes`, счётчик неудач подряд у источника вырос на единицу.

Вернуть парсер обратно на `quotes`.

- [ ] **Step 8: Коммит**

```bash
git add README.md docs/superpowers/specs/2026-09-18-runner-collector-integration-design.md
git commit -m "README раннера и поправка спеки про мягкую остановку"
```

---

## Проверка плана против спеки

| Требование спеки | Задача |
|---|---|
| Репозиторий с конвенциями dashboard (uv, ruff, Makefile, .env) | 1 |
| Парсер `quotes` без обвязки | 2 |
| Явный реестр, внятная ошибка на неизвестный ключ | 2 |
| JSONL: путь по slug, `.part` → rename, UTF-8 | 3 |
| Буфер логов: два источника, пачки ≤ 500, фильтр по уровню, блокировка | 4 |
| Конфигурация из окружения, падение без токена | 5 |
| Клиент: claim / logs / heartbeat / complete | 6 |
| Приведение params, маппинг счётчиков с `elapsed` | 7 |
| Парсеры чистые: `stream()` вычерпывает раннер | 8 |
| Heartbeat во время краула | 8 |
| Отказы: неизвестный парсер, падение краула с частичными данными, `max_requests`, недоступный `complete` с тремя попытками, потеря пачки логов | 8 |
| Отказ: недоступный control plane при `claim` | 9 |
| Отказ: Ctrl+C — мягкая остановка | 9, поправка спеки в 10 |
| Тесты без сети: MockTransport + локальный http.server | 6, 8 |
| CI: ruff + pytest | 1 |
| Ручная проверка end-to-end | 10 |
