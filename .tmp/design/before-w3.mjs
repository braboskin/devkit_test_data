import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/chats': [
    { id: 1, title: 'Прототип чата с агентом', updated_at: '2026-11-27T12:04:00Z' },
    { id: 2, title: 'Разбор входящих документов', updated_at: '2026-11-27T11:40:00Z' },
  ],
  '/api/agents': [
    { id: 1, name: 'Универсальный помощник', model: 'deepseek-chat' },
  ],
  '/api/home': { tasks: [], events: [], files: [] },
};

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1.5,
  });
  await context.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({ mode: 'dark', accent: '#334155', effects: true, background: 'none' }),
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
    ['chat', '/chat'],
    ['login', '/login'],
  ]) {
    await page.goto(`http://localhost:5173${path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(700);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/before-w3-${name}.png`,
    });
    console.log('shot', name, path);
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
