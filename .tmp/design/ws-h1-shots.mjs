import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const TODAY = new Date();
const at = (hour) => {
  const date = new Date(TODAY);
  date.setHours(hour, 0, 0, 0);
  return date.toISOString();
};
const LATER = new Date(Date.now() + 36 * 3600 * 1000).toISOString();

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': {
    data: { onboarding_done: true },
    summary: null,
    updated_at: null,
  },
  '/api/tasks': [
    {
      id: 1,
      title: 'Свести прототип чата с агентом',
      description: null,
      status: 'doing',
      priority: 'high',
      due_at: at(10),
      start_at: null,
      progress: 30,
      rrule: null,
      tags: ['Atlas'],
      project_id: null,
      sphere_id: 2,
      parent_id: null,
    },
    {
      id: 2,
      title: 'Утренний обзор дня',
      description: null,
      status: 'done',
      priority: 'medium',
      due_at: at(8),
      start_at: null,
      progress: 100,
      rrule: null,
      tags: [],
      project_id: null,
      sphere_id: 1,
      parent_id: null,
    },
    {
      id: 3,
      title: 'Разобрать входящие документы',
      description: null,
      status: 'todo',
      priority: 'medium',
      due_at: at(13),
      start_at: null,
      progress: 0,
      rrule: null,
      tags: [],
      project_id: null,
      sphere_id: null,
      parent_id: null,
    },
    {
      id: 4,
      title: 'Тренировка · ноги',
      description: null,
      status: 'todo',
      priority: 'low',
      due_at: at(19),
      start_at: null,
      progress: 0,
      rrule: null,
      tags: [],
      project_id: null,
      sphere_id: 1,
      parent_id: null,
    },
  ],
  '/api/spheres': [
    { id: 1, name: 'Здоровье' },
    { id: 2, name: 'Работа' },
  ],
  '/api/events': [
    {
      id: 1,
      title: 'Созвон с командой',
      description: null,
      start_at: LATER,
      end_at: null,
      all_day: false,
      location: null,
      rrule: null,
      project_id: null,
      sphere_id: null,
      remind_minutes: null,
    },
  ],
  '/api/documents?limit=5': [
    { id: 1, title: 'Стратегия Atlas на Q1', status: 'ready' },
    { id: 2, title: 'Заметки встречи с командой', status: 'processing' },
    { id: 3, title: 'Черновик статьи про личную ОС знаний', status: 'draft' },
  ],
  '/api/notifications?limit=20': { items: [], unread_count: 3 },
  '/api/goals': [{ id: 1, title: 'Цель' }],
  '/api/habits': [{ id: 1, title: 'Сон 7–8 часов' }],
  '/api/metrics': [{ id: 1, name: 'вес' }],
};

async function shot(browser, { name, theme, path, unauth }) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1.5,
  });
  await context.addInitScript((mode) => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({
        mode,
        accent: '#334155',
        effects: true,
        background: 'none',
      }),
    );
  }, theme);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/api/')) {
      await route.fallback();
      return;
    }
    if (unauth) {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Not authenticated' }),
      });
      return;
    }
    const key = `${url.pathname}${url.search}`;
    const body = MOCKS[key] ?? MOCKS[url.pathname] ?? [];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
  await page.goto(`http://localhost:5174${path}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await page.screenshot({
    path: `X:/devkit_projects/projects/atlas/.tmp/design/out/${name}.png`,
  });
  console.log('shot', name);
  await context.close();
}

async function main() {
  const browser = await chromium.launch();
  await shot(browser, { name: 'ws-h1-home-dark', theme: 'dark', path: '/' });
  await shot(browser, { name: 'ws-h1-home-light', theme: 'light', path: '/' });
  await shot(browser, {
    name: 'ws-h1-login-dark',
    theme: 'dark',
    path: '/',
    unauth: true,
  });
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
