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
  '/api/settings/llm': {
    configured: true,
    base_url: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
    masked: 'sk-…7f3a',
  },
  '/api/settings/llm/models': { models: ['deepseek-chat'], detail: null },
  '/api/settings/yadisk': { configured: false },
  '/api/settings/yadisk/config': { oauth_configured: true },
  '/api/settings/notifications': {
    reminders: true,
    quiet_start: null,
    quiet_end: null,
    max_push_per_day: 10,
  },
  '/api/settings/push-subscription': { configured: false, public_key: null },
  '/api/settings/worker-token': { configured: false, masked: null },
};

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
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
    ['settings', '/settings'],
    ['agents', '/settings/agents'],
    ['notifications', '/notifications'],
    ['jobs', '/jobs'],
    ['search', '/search'],
    ['space', '/space'],
  ]) {
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    await page.goto(`http://localhost:5173${path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/before-w6-${name}.png`,
    });
    console.log(name, 'errors:', errors.length, errors[0]?.slice(0, 100) ?? '');
    page.removeAllListeners('pageerror');
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
