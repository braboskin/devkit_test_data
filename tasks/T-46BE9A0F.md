---
id: T-46BE9A0F
project: atlas
epic: E-46E212B4
title: "Документы: обработка сканов на сервере (OCR) или явный выбор воркера"
status: done
type: feature
size: M
priority: medium
scope:
  - app/backend/**
  - tests/test_documents.py
  - tests/test_ingest_acceptance.py
verification:
  - unit-tests
  - ingest-fixtures
depends_on:
  - T-CA6FF8E2
plan_version: 1
report: docs/reports/T-46BE9A0F.md
assignee: agent:T-46BE9A0F/lead
created_at: 2026-11-21T21:22:12.064Z
updated_at: 2026-11-23T18:13:45.431Z
---

# Документы: обработка сканов на сервере (OCR) или явный выбор воркера

## Brief

Сейчас изображения и сканы-без-текста уходят в queued и ждут воркер на ПК (M2: OCR на ПК). Владелец считает это invalid UX: при отсутствии воркера документ «висит» без понятного результата. Нужно решить: (a) обработка OCR на сервере с лимитами и таймаутом, (b) явная кнопка «Обработать на сервере» для queued-документа (409/422, если сервер не может), (c) автофолбэк, если воркер не выходил на связь N минут. Acceptance: загруженный скан либо становится ready на сервере в рамках лимита, либо UI явно объясняет, что нужно и почему (без «вечного» queued). Ограничения VPS 4 ГБ и наличие tesseract учесть. Текст PDF уже обрабатывается на сервере до 200 стр/100 МБ (T-CA6FF8E2).
