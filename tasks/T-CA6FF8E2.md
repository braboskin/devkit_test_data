---
id: T-CA6FF8E2
project: testproject
epic: E-46E212B4
title: "M3 follow-up: UI — чат, конструктор агентов, онбординг, предложения"
status: in_progress
type: feature
size: L
priority: high
scope:
  - viewer/**
  - tests/test_web_build.py
verification:
  - unit-tests
  - web-build
depends_on:
  - T-B317AFAE
plan_version: 2
report: docs/reports/T-CA6FF8E2.md
assignee: owner
created_at: 2026-11-21T17:41:36.092Z
updated_at: 2026-11-21T21:35:01.642Z
---

# M3 follow-up: UI — чат, конструктор агентов, онбординг, предложения

## Brief

UI-слой M3: страница чата (SSE-стрим, цитаты, отмена), конструктор агента (имя, роль, инструкция, доступ к сферам/проектам, инструменты, модель, температура), интервью онбординга и экран профиля, карточки предложений «Применить/Отменить», форма LLM-ключа, минимальный экран «Сегодня» с запуском сценария. Контракт — API задачи T-B317AFAE; backend не менять. Закрывает UI-части A2, A4, A10, A14; A15/A16 (пауза сценария, сабагенты) — отдельно. Старт после T-B317AFAE (done).
