import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/web/package.json',
);
const { chromium } = require('@playwright/test');

const now = new Date();
const iso = (offsetDays, hours = 10) => {
  const d = new Date(now);
  d.setDate(d.getDate() + offsetDays);
  d.setHours(hours, 0, 0, 0);
  return d.toISOString();
};
const day = (offsetDays) => {
  const d = new Date(now);
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
};

const MOCKS = {
  '/api/me': { id: 'u1', username: 'mikhail' },
  '/api/profile': {
    data: { onboarding_done: true, name: 'Михаил' },
    summary: null,
    updated_at: null,
  },
  '/api/tasks': [
    { id: 2, title: 'Свести прототип чата с агентом', status: 'in_progress', priority: 'high', due_at: iso(0, 10), tags: [], sphere_id: 2, project_id: 1 },
    { id: 3, title: 'Разобрать входящие документы', status: 'todo', priority: 'medium', due_at: iso(0, 12), tags: [], sphere_id: 1, project_id: null },
    { id: 4, title: 'Тренировка · ноги', status: 'todo', priority: 'low', due_at: iso(0, 19), tags: [], sphere_id: 1, project_id: null },
    { id: 5, title: 'Планёрка по проекту', status: 'todo', priority: 'medium', due_at: iso(1, 11), tags: [], sphere_id: 2, project_id: 1 },
  ],
  '/api/spheres': [
    { id: 1, name: 'Здоровье', color: '#34d399' },
    { id: 2, name: 'Работа', color: '#3b82f6' },
  ],
  '/api/events': [
    { id: 1, title: 'Планёрка', start_at: iso(0, 16), end_at: iso(0, 17), all_day: false },
    { id: 2, title: 'Созвон с командой', start_at: iso(1, 12), end_at: iso(1, 13), all_day: false },
  ],
  '/api/documents': [
    { id: 1, title: 'Стратегия Atlas на Q1', mime: 'application/pdf', size_bytes: 24000, status: 'ready', created_at: iso(-1) },
    { id: 2, title: 'Заметки встречи с командой', mime: 'text/plain', size_bytes: 3200, status: 'processing', created_at: iso(0) },
  ],
  '/api/notifications': {
    items: [
      { id: 1, kind: 'task', title: 'Три задачи просрочены', body: 'Перенести на завтра?', link: '/tasks', read_at: null, created_at: iso(0, 9) },
    ],
    unread_count: 1,
  },
  '/api/proposals': [],
  '/api/habits': [
    { id: 1, title: 'Сон 7–8 часов', cadence: 'daily', target_per_period: 1, created_at: iso(-30), streak: 4, last_log: day(-1), today: true },
    { id: 2, title: 'Вода 2 л', cadence: 'daily', target_per_period: 1, created_at: iso(-30), streak: 2, last_log: day(0), today: true },
  ],
};

const requests = [];

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1.5,
  });
  await context.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({ mode: 'dark', accent: '#3b82f6', effects: true, background: 'none' }),
    );
  });
  const page = await context.newPage();
  page.on('request', (request) => {
    if (request.url().endsWith('/api/tasks') && request.method() === 'POST') {
      requests.push(request.postData() ?? '');
    }
  });
  await page.route('**/*', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (!pathname.startsWith('/api/')) {
      await route.fallback();
      return;
    }
    if (pathname === '/api/tasks' && route.request().method() === 'POST') {
      await route.fulfill({ status: 201, contentType: 'application/json', body: '{"id":9}' });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCKS[pathname] ?? []),
    });
  });
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));

  await page.goto('http://localhost:5174/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/home2-dark.png',
    fullPage: true,
  });

  await page.getByRole('button', { name: 'Задача' }).click();
  await page.getByLabel('Название').fill('Проверить быструю форму');
  await page.getByLabel('Срок').click();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Создать задачу' }).click();
  await page.waitForTimeout(500);
  const toastVisible = await page.getByText('Задача создана.').isVisible();
  const formClosed = (await page.getByLabel('Название').count()) === 0;
  console.log('form: toast=', toastVisible, 'closed=', formClosed, 'post=', requests[0] ?? 'none');
  console.log('desktop errors:', errors.length, errors[0]?.slice(0, 140) ?? '');

  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  await mobile.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({ mode: 'dark', accent: '#3b82f6', effects: true, background: 'none' }),
    );
  });
  const mobilePage = await mobile.newPage();
  await mobilePage.route('**/*', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (!pathname.startsWith('/api/')) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCKS[pathname] ?? []),
    });
  });
  await mobilePage.goto('http://localhost:5174/', { waitUntil: 'networkidle' });
  await mobilePage.waitForTimeout(600);
  const overflow = await mobilePage.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  await mobilePage.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/home2-mobile-dark.png',
    fullPage: true,
  });
  console.log('mobile overflow px:', overflow);

  await mobile.close();
  await context.close();
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
