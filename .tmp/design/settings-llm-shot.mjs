import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
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
  '/api/settings/yadisk': { configured: false },
  '/api/settings/yadisk/config': { oauth_configured: true },
  '/api/settings/notifications': {
    reminders: true,
    quiet_start: null,
    quiet_end: null,
    max_push_per_day: 10,
  },
  '/api/settings/push-subscription': { configured: false, public_key: null },
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
    await page.goto('http://localhost:5173/settings', { waitUntil: 'networkidle' });
    await page.waitForTimeout(900);
    const provider = await page
      .getByLabel('Провайдер')
      .first()
      .isVisible()
      .catch(() => false);
    const model = await page
      .getByLabel('Модель')
      .first()
      .isVisible()
      .catch(() => false);
    console.log('theme', theme, 'provider', provider, 'model', model);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/settings-llm-${theme}.png`,
    });
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
