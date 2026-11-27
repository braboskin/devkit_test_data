---
id: T-E4E99EF8
project: atlas
epic: E-AA7F23F1
title: "Уведомления: автообновление списка и счётчика"
status: needs_review
type: feature
size: S
priority: medium
scope:
  - repo/atlas/viewer/src/pages/notifications
  - repo/atlas/viewer/src/app
verification:
  - web-build
  - typecheck-web
  - lint-web
  - arch-web
depends_on:
  - T-AC2A5666
plan_version: 1
report: docs/reports/T-E4E99EF8.md
assignee: agent
created_at: 2026-11-27T13:37:41.767Z
updated_at: 2026-11-27T15:07:49.940Z
---

# Уведомления: автообновление списка и счётчика

## Brief

Лента уведомлений обновляется только при заходе. Добавить интервал (POLL_MS) с очисткой, порог и остановку на скрытой вкладке; обновлять бейдж в шапке.
