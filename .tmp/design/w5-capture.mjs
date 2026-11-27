import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/agents': [{ id: 1, name: 'Универсальный помощник', model: 'deepseek-chat' }],
  '/api/spheres': [
    { id: 1, name: 'Здоровье', color: '#34d399', description: 'Сон, спорт, питание' },
    { id: 2, name: 'Работа', color: '#3b82f6', description: null },
  ],
  '/api/projects': [
    { id: 1, name: 'Atlas', sphere_id: 2, status: 'active', progress: 40 },
  ],
  '/api/people': [
    { id: 1, name: 'Анна Петрова', tags: ['работа'], phone: null, photo_ref: null },
  ],
  '/api/people/1': {
    id: 1,
    name: 'Анна Петрова',
    tags: ['работа'],
    notes: null,
    photo_ref: null,
    spheres: [],
    projects: [],
  },
};

async function main() {
  const browser = await chromium.launch();
  for (const theme of ['dark', 'light']) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 960 },
      deviceScaleFactor: 1.5,
    });
    await context.addInitScript((mode) => {
      window.localStorage.setItem(
        'atlas.theme',
        JSON.stringify({ mode, accent: '#334155', effects: true, background: 'none' }),
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
    for (const [name, path] of [
      ['spheres', '/spheres'],
      ['projects', '/projects'],
      ['people', '/people'],
      ['profile', '/profile'],
      ['growth', '/growth'],
    ]) {
      await page.goto(`http://localhost:5173${path}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(800);
      await page.screenshot({
        path: `X:/devkit_projects/projects/atlas/.tmp/design/out/after-w5-${name}-${theme}.png`,
      });
    }
    console.log('ok', theme);
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
