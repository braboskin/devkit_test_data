import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/spheres': [
    { id: 1, name: 'Здоровье', color: '#34d399' },
    { id: 2, name: 'Работа', color: '#60a5fa' },
    { id: 3, name: 'Обучение', color: '#c084fc' },
  ],
  '/api/projects': [{ id: 1, name: 'Atlas', sphere_id: 2 }],
  '/api/events': [
    {
      id: 1,
      title: 'Планёрка команды',
      start_at: '2026-11-27T10:00:00',
      end_at: '2026-11-27T11:00:00',
      all_day: false,
      sphere_id: 2,
      project_id: 1,
      rrule: 'FREQ=WEEKLY;BYDAY=FR',
      remind_minutes: 5,
    },
    {
      id: 2,
      title: 'Тренировка',
      start_at: '2026-11-27T19:00:00',
      end_at: '2026-11-27T20:30:00',
      all_day: false,
      sphere_id: 1,
      project_id: null,
      rrule: null,
      remind_minutes: 15,
    },
    {
      id: 3,
      title: 'Дедлайн по документам',
      start_at: '2026-11-29T00:00:00',
      end_at: null,
      all_day: true,
      sphere_id: 2,
      project_id: null,
      rrule: null,
      remind_minutes: null,
    },
    {
      id: 4,
      title: 'Курс по системному дизайну',
      start_at: '2026-12-02T18:00:00',
      end_at: '2026-12-02T19:30:00',
      all_day: false,
      sphere_id: 3,
      project_id: null,
      rrule: null,
      remind_minutes: 10,
    },
  ],
};

const VIEWS = ['Месяц', 'Неделя', 'День', 'Год', 'Агенда'];

async function shoot(page, name) {
  await page.screenshot({
    path: `X:/devkit_projects/projects/atlas/.tmp/design/out/w4-calendar-${name}.png`,
  });
  console.log('shot', name);
}

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
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCKS[pathname] ?? []),
      });
    });
    await page.goto('http://localhost:5174/calendar', { waitUntil: 'networkidle' });
    await page.waitForTimeout(900);
    for (const view of VIEWS) {
      const button = page.getByRole('button', { name: view, exact: true });
      await button.click();
      await page.waitForTimeout(500);
      await shoot(page, `${theme}-${view.toLowerCase()}`);
    }
    console.log('errors', theme, errors.length, errors[0]?.slice(0, 160) ?? '');
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
