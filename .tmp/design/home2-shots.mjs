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
    { id: 1, title: 'Утренний обзор дня', status: 'done', priority: 'medium', due_at: iso(0, 8), tags: [], sphere_id: 3, project_id: null },
    { id: 2, title: 'Свести прототип чата с агентом', status: 'in_progress', priority: 'high', due_at: iso(0, 10), tags: [], sphere_id: 2, project_id: 1 },
    { id: 3, title: 'Разобрать входящие документы', status: 'todo', priority: 'medium', due_at: iso(0, 12), tags: [], sphere_id: 1, project_id: null },
    { id: 4, title: 'Тренировка · ноги', status: 'todo', priority: 'low', due_at: iso(0, 19), tags: [], sphere_id: 1, project_id: null },
    { id: 5, title: 'Планёрка по проекту', status: 'todo', priority: 'medium', due_at: iso(1, 11), tags: [], sphere_id: 2, project_id: 1 },
    { id: 6, title: 'Ревью макетов', status: 'todo', priority: 'high', due_at: iso(2, 15), tags: [], sphere_id: 2, project_id: 1 },
    { id: 7, title: 'Чтение 20 минут', status: 'todo', priority: 'low', due_at: iso(3, 21), tags: [], sphere_id: 4, project_id: null },
  ],
  '/api/spheres': [
    { id: 1, name: 'Здоровье', color: '#34d399' },
    { id: 2, name: 'Работа', color: '#3b82f6' },
    { id: 3, name: 'Ритм', color: '#a78bfa' },
    { id: 4, name: 'Развитие', color: '#f472b6' },
  ],
  '/api/events': [
    { id: 1, title: 'Планёрка', start_at: iso(0, 16), end_at: iso(0, 17), all_day: false },
    { id: 2, title: 'Созвон с командой', start_at: iso(1, 12), end_at: iso(1, 13), all_day: false },
    { id: 3, title: 'День без встреч', start_at: iso(2, 0), end_at: null, all_day: true },
  ],
  '/api/documents': [
    { id: 1, title: 'Стратегия Atlas на Q1', mime: 'application/pdf', size_bytes: 24000, status: 'ready', created_at: iso(-1) },
    { id: 2, title: 'Заметки встречи с командой', mime: 'text/plain', size_bytes: 3200, status: 'processing', created_at: iso(0) },
    { id: 3, title: 'Черновик статьи про личную ОС знаний', mime: 'text/plain', size_bytes: 1200, status: 'uploaded', created_at: iso(-3) },
    { id: 4, title: 'Отчёт по выручке', mime: 'application/pdf', size_bytes: 41000, status: 'ready', created_at: iso(-5) },
    { id: 5, title: 'Конспект главы 4', mime: 'text/plain', size_bytes: 900, status: 'needs_review', created_at: iso(-6) },
  ],
  '/api/notifications': {
    items: [
      { id: 1, kind: 'task', title: 'Три задачи просрочены', body: 'Перенести на завтра?', link: '/tasks', read_at: null, created_at: iso(0, 9) },
      { id: 2, kind: 'document', title: 'Документ обработан', body: 'Стратегия Atlas на Q1', link: '/files/1', read_at: null, created_at: iso(0, 8) },
    ],
    unread_count: 2,
  },
  '/api/proposals': [
    { id: 1, kind: 'task_batch', payload: {}, status: 'pending', created_at: iso(0, 7), applied_at: null },
  ],
  '/api/habits': [
    { id: 1, title: 'Сон 7–8 часов', cadence: 'daily', target_per_period: 1, created_at: iso(-30), streak: 4, last_log: day(-1), today: true },
    { id: 2, title: 'Вода 2 л', cadence: 'daily', target_per_period: 1, created_at: iso(-30), streak: 2, last_log: day(0), today: true },
    { id: 3, title: '8k шагов', cadence: 'daily', target_per_period: 1, created_at: iso(-30), streak: 6, last_log: day(-2), today: false },
    { id: 4, title: 'Чтение 20 минут', cadence: 'daily', target_per_period: 1, created_at: iso(-30), streak: 1, last_log: day(-1), today: true },
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
        JSON.stringify({ mode, accent: '#3b82f6', effects: true, background: 'none' }),
      );
    }, theme);
    const page = await context.newPage();
    await page.route('**/*', async (route) => {
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
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    await page.goto('http://localhost:5174/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(700);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/home2-${theme}.png`,
      fullPage: true,
    });
    if (theme === 'dark') {
      await page.getByRole('button', { name: 'Задача' }).click();
      await page.waitForTimeout(300);
      await page.screenshot({
        path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/home2-quick-form-dark.png',
      });
    }
    console.log(theme, 'errors:', errors.length, errors[0]?.slice(0, 160) ?? '');
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
