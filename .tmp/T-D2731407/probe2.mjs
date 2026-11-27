import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'mihail', display_name: 'Михаил', is_owner: true },
  '/api/profile': {
    data: { onboarding_done: true, ui: { background_ref: 'demo' } },
    summary: 'Сферы: Здоровье, Работа; Проекты: Atlas',
    updated_at: null,
  },
  '/api/notifications': { items: [], unread_count: 0 },
};

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.addInitScript(() => {
  window.localStorage.setItem(
    'atlas.theme',
    JSON.stringify({ mode: 'dark', accent: '#334155', effects: true, background: 'none' }),
  );
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error.message)));
page.on('console', (message) => {
  if (message.type() === 'error') errors.push('console: ' + message.text().slice(0, 200));
});
await page.route('**/api/**', async (route) => {
  const url = new URL(route.request().url());
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(MOCKS[url.pathname] ?? []),
  });
});
for (const path of ['/profile', '/settings']) {
  await page.goto('http://localhost:5174' + path);
  await page.waitForTimeout(3000);
  const text = await page.evaluate(() => document.body.innerText.slice(0, 1200));
  console.log('==== ' + path + ' ====');
  console.log(text);
}
console.log('==== errors ====');
console.log(errors.slice(0, 10).join('\n'));
await context.close();
await browser.close();
