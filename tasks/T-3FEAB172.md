---
id: T-3FEAB172
project: atlas
epic: E-AA7F23F1
title: "Настройки и Задания: рестайл на дизайн-системе"
status: needs_review
type: feature
size: M
priority: medium
scope:
  - repo/atlas/viewer/src/pages/settings
  - repo/atlas/viewer/src/pages/jobs
verification:
  - web-build
  - typecheck-web
  - lint-web
  - arch-web
depends_on:
  - T-84858592
plan_version: 1
report: docs/reports/T-3FEAB172.md
assignee: owner
created_at: 2026-11-27T13:37:42.524Z
updated_at: 2026-11-27T15:36:50.584Z
---

# Настройки и Задания: рестайл на дизайн-системе

## Brief

Единственные оставшиеся экраны на нативном HTML: settings и jobs. Перевести формы/таблицы/кнопки на обёртки shared/ui, сохранить интеграции, уведомления, воркер и отмену заданий.
