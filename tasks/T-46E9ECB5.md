---
id: T-46E9ECB5
project: atlas
epic: E-AA7F23F1
title: "Файлы: серверная пагинация и фильтры"
status: planned
type: feature
size: M
priority: medium
scope:
  - repo/atlas/app/features/documents
  - repo/atlas/viewer/src/pages/files
  - repo/atlas/shared/api
verification:
  - unit-tests
  - lint-python
  - typecheck-python
  - arch-python
  - web-build
  - typecheck-web
  - lint-web
  - arch-web
depends_on:
  - T-AC2A5666
plan_version: 1
report: docs/reports/T-46E9ECB5.md
assignee: null
created_at: 2026-11-27T13:37:39.879Z
updated_at: 2026-11-27T14:17:02.338Z
---

# Файлы: серверная пагинация и фильтры

## Brief

Дерево файлов грузит /api/documents целиком — при тысячах файлов нужны серверные фильтры по сфере/проекту/статусу и пагинация; обновить viewer под новый контракт.
