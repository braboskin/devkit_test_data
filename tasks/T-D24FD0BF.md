---
id: T-D24FD0BF
project: atlas
epic: E-710FC7ED
title: "Подключение LLM: провайдер, ключ, список моделей"
status: planned
type: feature
size: L
priority: high
scope:
  - app/backend/features/settings/**
  - app/backend/features/agent/llm.py
  - viewer/src/shared/ui/**
  - viewer/src/shared/lib/llmProviders.ts
  - viewer/src/shared/api/index.ts
  - viewer/src/pages/settings/ui/Settings.tsx
  - viewer/src/app/SetupWizard.tsx
  - tests/test_agent_llm.py
  - tests/test_isolation.py
  - tests/test_settings_models.py
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
  - T-4FC8A97B
plan_version: 1
report: docs/reports/T-D24FD0BF.md
assignee: null
created_at: 2026-11-27T16:09:38.110Z
updated_at: 2026-11-27T17:37:53.082Z
---

# Подключение LLM: провайдер, ключ, список моделей

## Brief

Один LlmSettingsForm в shared/ui: провайдер → адрес API (только для «Свой») → ключ (placeholder sk-..., password) → модель (input+datalist). Список моделей — новый POST /api/settings/llm/models (ключ не уходит в браузер, TRANSPORT подменяем), при отказе — каталог и ручной ввод. PUT /api/settings/llm принимает пустой api_key (сохраняется прежний). Компонент в SetupWizard.ModelStep и в секции «Модель» на /settings; провайдер выводится из base_url. Матрица test_isolation обновлена.

Провайдер — antd Select, модель — antd AutoComplete (подсказки из списка провайдера + свободный ввод id для «Своего»), не input+datalist.
