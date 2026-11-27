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
  ],
};

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1.5,
  });
  await context.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({ mode: 'dark', accent: '#334155', effects: true, background: 'none' }),
    );
  });
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
  await page.waitForTimeout(800);

  // Создание события: клик по пустому дню.
  await page.locator('.fc-daygrid-day').nth(15).click();
  await page.waitForTimeout(400);
  const dialogVisible = await page.getByRole('dialog').isVisible().catch(() => false);
  console.log('dialog visible:', dialogVisible);
  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/w4-calendar-dialog.png',
  });

  // «Сегодня» и редактирование события.
  await page.getByRole('button', { name: 'Отмена' }).click();
  await page.waitForTimeout(300);
  await page.getByRole('button', { name: 'Сегодня' }).click();
  await page.waitForTimeout(400);
  console.log('errors:', errors.length, errors[0]?.slice(0, 160) ?? '');
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
