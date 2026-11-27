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
      ['calendar', '/calendar'],
      ['tasks', '/tasks'],
      ['files', '/files'],
    ]) {
      await page.goto(`http://localhost:5173${path}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(900);
      await page.screenshot({
        path: `X:/devkit_projects/projects/atlas/.tmp/design/out/after-w4-${name}-${theme}.png`,
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
