---
id: T-4FC8A97B
project: atlas
epic: E-710FC7ED
title: "Дизайн-система: токены, Emotion, шрифт, motion, примитивы, каркас"
status: inbox
type: feature
size: L
priority: high
scope:
  - viewer/src/shared/ui/**
  - viewer/src/shared/lib/theme.ts
  - viewer/src/app/AppShell.tsx
  - viewer/src/app/App.tsx
  - viewer/src/app/main.tsx
  - viewer/src/app/styles/**
  - viewer/src/app/styles.css
  - viewer/public/fonts/**
  - viewer/package.json
  - viewer/package-lock.json
  - viewer/index.html
  - viewer/e2e/**
  - docs/DESIGN.md
verification:
  - web-build
  - typecheck-web
  - lint-web
  - arch-web
  - e2e
  - a11y
  - format-web
depends_on: []
plan_version: 0
report: docs/reports/T-4FC8A97B.md
assignee: null
created_at: 2026-11-27T16:09:29.548Z
updated_at: 2026-11-27T16:09:29.548Z
---

# Дизайн-система: токены, Emotion, шрифт, motion, примитивы, каркас

## Brief

Graphite-дизайн-система: tokens.css (light/dark, акцент из theme.ts, дефолт #334155), Emotion + Global, Roboto Condensed self-host, LazyMotion, примитивы shared/ui без смены публичного API, AppShell с боковым меню и топбаром, vendor.ts для antd/SVAR/FullCalendar/Recharts, docs/DESIGN.md. Удаляются styles.css/base.css/shell.css/ui.css. antd-first: Avatar → antd Avatar, Skeleton → antd Skeleton, Badge/DocBadge/JobBadge → antd Tag, TreeList → antd Tree, Empty → antd Empty, дубль EmptyState в States.tsx удалить; мобильный сайдбар — antd Drawer, топбар — Tooltip/Dropdown; токены antd через ConfigProvider (Card, Segmented, Switch, Tag, Result, Drawer).
