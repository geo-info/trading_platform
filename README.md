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
uv sync                                           # зависимости
uv run python -m trading.run_all                  # все площадки разом
uv run python -m trading.run_all centerr etb      # только названные
uv run python -m trading.run_all --max-pages 2    # короткий прогон
uv run python -m trading.run_all --list           # что вообще есть
uv run python -m trading.parsers.bep              # одна площадка отдельно
```

Адрес базы берётся из `--mongo-uri`, иначе из `$MONGO_URI`, иначе локальная
`mongodb://localhost:27017`. Имя базы — из `$MONGO_DB`, по умолчанию `trading`.

## Разработка

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```
