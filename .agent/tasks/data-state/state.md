# Task State

## Objective
Сохранить снимок, исправить сбор/представление торгов по архитектурному обзору.

## Current phase
review complete

## Decisions made
Чистые reducers + Mongo CAS. Неизвестная активность null. Миграция только
при остановленных парсерах. LIMIT=1000 сохранён.

## Current assumptions
detail_at — нижняя граница начала прогона, даты источников — Europe/Moscow.

## Tests / validation
196 passed, 4 live deselected; REQUIRE_MONGO=1; Ruff check/format, diff check pass.

## Open questions / Next action
После пользовательского сбора выполнить аудит данных; исправить контракт
is_active в ETL перед PostGIS. Базы и ETL в этой задаче не изменялись.

## Files touched / Artifacts
Список в git diff fb7c65f; docs/plans/2026-10-09-data-state.md.
Локальные report/diff/XML: data/reviews/2026-10-09/fixes/.

## Last known good point
main: fb7c65f — исходный снимок. Исправления: codex/data-state-consistency.

## Передача в следующую сессию — 2026-10-18

Сохранены последующие изменения: удалён written_at из новых записей;
добавлен `python -m tp.scripts.detail_progress` с общим фильтром очереди;
сохранены пользовательские настройки zakazrf: concurrency=1, max_errors=10.
По последнему сообщению пользователя сайт zakazrf недоступен, оставались
443 из 1000 лотов. Эти числа исторические, на 18 октября не перепроверены.

Проверки 18 октября: 173 теста прошли; 25 Mongo-тестов не запустились,
так как localhost:27017 недоступен. Ruff check и format --check прошли.
Ранее Mongo-тесты проходили; перед дальнейшими изменениями повторить их
с работающей Mongo и REQUIRE_MONGO=1. Рабочие базы не изменялись.

GitHub origin: geo-info/trading_platform. SSH требует проверки ключа хоста;
HTTPS работает через временный `git -c url.https://github.com/.insteadOf=git@github.com:`.
Продолжать с ветки codex/data-state-consistency. Другие удалённые ветки не объединялись.
ETL пользователь перенёс в отдельную сессию: сначала проверить актуальное
состояние связанного репозитория, не предполагать, что с 9 октября он не менялся.
