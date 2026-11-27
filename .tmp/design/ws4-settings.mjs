import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/web/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил', avatar_ref: null },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/agents': [{ id: 1, name: 'Ассистент', model: 'deepseek-chat' }],
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
    quiet_start: '23:00',
    quiet_end: '08:00',
    max_push_per_day: 10,
  },
  '/api/settings/push-subscription': { configured: false, public_key: null },
  '/api/settings/worker-token': { configured: false, masked: null },
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
  await page.goto('http://localhost:5199/settings', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  const textarea = page.locator('textarea.ant-input').first();
  const box = (await textarea.count()) ? await textarea.boundingBox() : null;
  console.log('textarea height:', box ? Math.round(box.height) : null);

  const switchRow = page.locator('.ant-switch').first();
  console.log('switch rows present:', await page.locator('.ant-switch').count());
  console.log('switch height:', (await switchRow.count()) ? Math.round((await switchRow.boundingBox()).height) : null);

  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/ws4-settings-dark.png',
  });
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
