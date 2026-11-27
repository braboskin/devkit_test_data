---
id: T-EAD5B055
project: atlas
epic: E-710FC7ED
title: Переименование viewer/ в web/
status: planned
type: chore
size: L
priority: high
scope:
  - viewer/**
  - devkit.yaml
  - .github/workflows/ci.yml
  - .pre-commit-config.yaml
  - pyproject.toml
  - app/backend/main.py
  - tests/**
  - AGENTS.md
  - README.md
  - app/README.md
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
  - T-D24FD0BF
  - T-59D31937
  - T-F4778357
  - T-7805803A
  - T-28C2A79F
  - T-7E446096
plan_version: 1
report: docs/reports/T-EAD5B055.md
assignee: null
created_at: 2026-11-27T16:10:14.649Z
updated_at: 2026-11-27T20:37:21.521Z
---

# Переименование viewer/ в web/

## Brief

git mv viewer web и синхронная правка живых ссылок: npm-имя atlas-web, devkit.yaml (7 cwd, install-web), CI artifact web-dist, pre-commit, pyproject exclude, main.py (ROOT/web/dist, mount name web), тесты (test_viewer_acceptance.py -> test_web_acceptance.py, пути), AGENTS/README. Имена проверок профиля не меняются; архив docs/coordination/archive/DEVKIT.md не переписывается. Идёт последней, чтобы не конфликтовать по путям.
