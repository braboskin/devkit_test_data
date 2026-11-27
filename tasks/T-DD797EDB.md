---
id: T-DD797EDB
project: atlas
epic: E-AA7F23F1
title: "Бэкенд: миграции и эндпоинты под новый UI"
status: needs_review
type: feature
size: L
priority: high
scope:
  - app/backend
  - alembic/versions
  - tests
  - viewer/src/shared/api
verification:
  - unit-tests
  - lint-python
  - typecheck-python
  - arch-python
  - schema-check
depends_on: []
plan_version: 1
report: docs/reports/T-DD797EDB.md
assignee: agent
created_at: 2026-11-27T00:20:46.428Z
updated_at: 2026-11-27T10:59:31.212Z
---

# Бэкенд: миграции и эндпоинты под новый UI

## Brief

TZ-53B42870 раздел 11. Миграции: цвет/иконка/описание интереса, start_at и progress задачи, start_at проекта, User.display_name и avatar_ref, Person.photo_ref, per-user timezone. Эндпоинты: upload и ресайз аватара и фона, summary интереса и проекта, search?scope=all. Тесты изоляции и новых маршрутов.
