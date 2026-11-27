import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/web/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил', display_name: 'Михаил' },
  '/api/profile': {
    data: { onboarding_done: true, name: 'Михаил', age: 34, city: 'Москва', occupation: 'Дизайнер' },
    summary: 'Продуктовый дизайнер',
    updated_at: null,
  },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/agents': [{ id: 1, name: 'Универсальный помощник', model: 'deepseek-chat' }],
  '/api/spheres': [
    { id: 1, name: 'Здоровье', color: '#34d399', description: 'Сон и спорт' },
    { id: 2, name: 'Работа', color: '#3b82f6', description: null },
  ],
  '/api/projects': [{ id: 1, name: 'Atlas', sphere_id: 2, status: 'active' }],
  '/api/projects/1': { id: 1, name: 'Atlas', sphere_id: 2, status: 'active', description: null },
  '/api/spheres/1': {
    id: 1,
    name: 'Здоровье',
    color: '#34d399',
    description: 'Сон и спорт',
    tasks: 5,
    tasks_done: 3,
    projects: [],
  },
  '/api/growth/habits': [],
  '/api/growth/goals': [],
  '/api/documents': [],
};

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1.4,
  });
  await context.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({ mode: 'dark', accent: '#3b82f6', effects: true, background: 'none' }),
    );
  });
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

  for (const [name, path] of [
    ['home', '/'],
    ['growth', '/growth'],
    ['people', '/people'],
    ['profile', '/profile'],
    ['project', '/projects/1'],
    ['sphere', '/spheres/1'],
    ['settings', '/settings'],
    ['chat', '/chat'],
  ]) {
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    await page.goto(`http://localhost:5173${path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(700);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/w12-${name}-dark.png`,
      fullPage: true,
    });
    console.log(name, 'errors:', errors.length, errors[0]?.slice(0, 90) ?? '');
    page.removeAllListeners('pageerror');
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
