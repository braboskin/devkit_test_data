---
id: T-DB0D3FD0
project: atlas
epic: E-AA7F23F1
title: "Онбординг: маршруты /setup/*, deep links, баннер пропуска и серверная идемпотентность"
status: inbox
type: feature
size: M
priority: medium
scope:
  - repo/atlas/viewer/src/app
  - repo/atlas/viewer/src/pages/onboarding
  - repo/atlas/viewer/src/pages/home
  - repo/atlas/app/features/onboarding
verification:
  - web-build
  - typecheck-web
  - lint-web
  - arch-web
  - unit-tests
  - lint-python
  - typecheck-python
depends_on:
  - T-6E58E324
plan_version: 0
report: docs/reports/T-DB0D3FD0.md
assignee: null
created_at: 2026-11-27T13:37:41.027Z
updated_at: 2026-11-27T13:37:41.027Z
---

# Онбординг: маршруты /setup/*, deep links, баннер пропуска и серверная идемпотентность

## Brief

Поток в гейте App без deep links; id хранятся в localStorage. Добавить маршруты /login,/setup/model,/setup/disk,/survey с возобновлением по URL, баннер «опрос пропущен» на Главной, серверную идемпотентность (OnboardingSession).
