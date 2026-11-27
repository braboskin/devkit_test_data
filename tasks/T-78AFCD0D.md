---
id: T-78AFCD0D
project: atlas
epic: E-710FC7ED
title: "Чат: поиск по диалогам, «Стоп», «Глубокий анализ», вложения"
status: inbox
type: feature
size: L
priority: medium
scope:
  - viewer/src/pages/chat/**
  - viewer/src/shared/api/index.ts
  - app/backend/features/agent/**
  - tests/test_agent_chat.py
  - tests/test_isolation.py
  - viewer/e2e/**
verification:
  - web-build
  - typecheck-web
  - lint-web
  - arch-web
  - e2e
  - a11y
  - unit-tests
  - lint-python
  - typecheck-python
  - arch-python
depends_on:
  - T-F4778357
plan_version: 1
report: docs/reports/T-78AFCD0D.md
assignee: null
created_at: 2026-11-27T18:31:01.854Z
updated_at: 2026-11-27T18:34:29.174Z
---

# Чат: поиск по диалогам, «Стоп», «Глубокий анализ», вложения

## Brief

Довести чат до ТЗ эпика E-AA7F23F1 §6.2. Сейчас отсутствуют: (1) поиск по диалогам — клиентский фильтр по загруженному списку /api/chats; (2) кнопка «Стоп» во время стрима — бэкенд уже умеет POST /api/chats/{id}/messages/{mid}/cancel, нужно связать с UI и SSE; (3) переключатель «Глубокий анализ» — требует решения владельца о семантике (больше контекста / другая модель / другой промпт) и, вероятно, флага в MessageIn; (4) вложения в композере — нужен контракт MessageIn.document_ids и передача выбранных документов в контекст агента. Ничего из этого не входит в дизайн-перевод T-F4778357, поэтому отдельная задача после него.
