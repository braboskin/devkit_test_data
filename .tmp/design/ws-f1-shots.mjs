import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': {
    data: { onboarding_done: true, timezone: 'Europe/Moscow' },
    summary: 'Личная операционная система знаний.',
    updated_at: '2026-11-27T10:00:00Z',
  },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/settings/llm': {
    configured: true,
    base_url: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
    masked: 'sk-…7f3a',
  },
  '/api/settings/llm/models': {
    models: ['deepseek-chat', 'deepseek-reasoner'],
    detail: null,
  },
  '/api/settings/yadisk': {
    configured: true,
    masked: 'y0_Ag…9xQ',
  },
  '/api/settings/yadisk/config': { oauth_configured: true },
  '/api/settings/notifications': {
    reminders: true,
    quiet_start: '23:00',
    quiet_end: '08:00',
    max_push_per_day: 10,
  },
  '/api/settings/push-subscription': {
    enabled: true,
    subscribed: false,
    public_key: 'BExampleKey',
  },
};

async function main() {
  const browser = await chromium.launch();
  for (const theme of ['dark', 'light']) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 },
      deviceScaleFactor: 1.5,
    });
    await context.addInitScript((mode) => {
      window.localStorage.setItem(
        'atlas.theme',
        JSON.stringify({
          mode,
          accent: '#334155',
          effects: true,
          background: 'none',
        }),
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
    await page.goto('http://localhost:5173/settings', {
      waitUntil: 'networkidle',
    });
    await page.waitForTimeout(900);
    const errors = await page.evaluate(() => window.__errors ?? []);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/ws-f1-settings-${theme}.png`,
      fullPage: true,
    });
    console.log('ok', theme, 'pageerrors', errors.length);
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
