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
