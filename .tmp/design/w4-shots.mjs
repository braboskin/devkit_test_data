import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const TASKS = [
  {
    id: 1,
    title: 'Свести прототип чата с агентом',
    status: 'doing',
    priority: 'high',
    due_at: '2026-11-27T10:00:00',
    project_id: 1,
    sphere_id: 1,
    parent_id: null,
    rrule: null,
    tags: ['чат', 'дизайн'],
    description: 'Собрать каркас диалога и композер.',
  },
  {
    id: 2,
    title: 'Разобрать входящие документы',
    status: 'todo',
    priority: 'medium',
    due_at: '2026-11-25T12:30:00',
    project_id: null,
    sphere_id: 2,
    parent_id: null,
    rrule: null,
    tags: [],
    description: null,
  },
  {
    id: 3,
    title: 'Утренний обзор дня',
    status: 'done',
    priority: 'low',
    due_at: '2026-11-27T08:10:00',
    project_id: null,
    sphere_id: 3,
    parent_id: null,
    rrule: 'FREQ=DAILY',
    tags: ['ритм'],
    description: null,
  },
  {
    id: 4,
    title: 'Проверить отчёт по индексации',
    status: 'cancelled',
    priority: 'medium',
    due_at: null,
    project_id: 1,
    sphere_id: 1,
    parent_id: null,
    rrule: null,
    tags: [],
    description: null,
  },
];

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/tasks': TASKS,
  '/api/tasks/1': {
    blocked_by: [],
    subtasks: [{ id: 4, title: 'Проверить отчёт по индексации', status: 'cancelled' }],
    people: [{ person_id: 1, name: 'Анна', role: 'дизайнер' }],
    status: 'doing',
  },
  '/api/projects': [
    { id: 1, name: 'Atlas', sphere_id: 1 },
    { id: 2, name: 'Личный сайт', sphere_id: 2 },
  ],
  '/api/people': [{ id: 1, name: 'Анна' }],
  '/api/spheres': [
    { id: 1, name: 'Работа', color: '#334155' },
    { id: 2, name: 'Знания', color: '#0ea5e9' },
    { id: 3, name: 'Ритм', color: '#22c55e' },
  ],
  '/api/documents': [
    {
      id: 1,
      title: 'Стратегия Atlas на Q1',
      status: 'ready',
      sphere_id: 1,
      project_id: 1,
      created_at: '2026-11-26T10:00:00',
      mime: 'application/pdf',
      size_bytes: 120000,
      tags: ['стратегия'],
    },
    {
      id: 2,
      title: 'Заметки встречи с командой',
      status: 'processing',
      sphere_id: 1,
      project_id: null,
      created_at: '2026-11-27T09:12:00',
      mime: 'text/markdown',
      size_bytes: 4000,
      tags: [],
    },
    {
      id: 3,
      title: 'Черновик статьи про личную ОС знаний',
      status: 'needs_review',
      sphere_id: 2,
      project_id: null,
      created_at: '2026-11-25T18:00:00',
      mime: 'text/plain',
      size_bytes: 8000,
      tags: ['статья'],
    },
  ],
};

async function main() {
  const browser = await chromium.launch();
  for (const theme of ['dark', 'light']) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      deviceScaleFactor: 1.5,
    });
    await context.addInitScript((mode) => {
      window.localStorage.setItem(
        'atlas.theme',
        JSON.stringify({ mode, accent: '#334155', effects: true, background: 'none' }),
      );
    }, theme);
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    await page.route('**/*', async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (!pathname.startsWith('/api/')) {
        await route.fallback();
        return;
      }
      const body = MOCKS[pathname];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body ?? []),
      });
    });
    for (const [name, path] of [
      ['tasks', '/tasks'],
      ['files', '/files'],
    ]) {
      await page.goto(`http://localhost:5173${path}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(700);
      await page.screenshot({
        path: `X:/devkit_projects/projects/atlas/.tmp/design/out/after-w4-${name}-${theme}.png`,
      });
    }
    console.log(theme, 'errors:', errors.length, errors[0]?.slice(0, 140) ?? '');
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
