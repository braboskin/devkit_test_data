import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/web/package.json',
);
const { chromium } = require('@playwright/test');

const PROFILE = {
  onboarding_done: true,
  name: 'Михаил',
  age: 34,
  city: 'Москва',
  occupation: 'Продуктовый дизайнер',
  preferences: { about: 'люблю системность' },
};

const MOCKS = {
  '/api/me': { id: 'u1', username: 'mikhail', avatar_ref: null },
  '/api/profile': { data: PROFILE, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
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
    viewport: { width: 1440, height: 1100 },
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
    const body = MOCKS[pathname];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body ?? []),
    });
  });
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));

  await page.goto('http://localhost:5188/settings', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/ws2-settings-profile-dark.png',
    fullPage: true,
  });

  await page.getByRole('button', { name: 'Изменить пароль' }).click();
  await page.waitForTimeout(400);
  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/ws2-password-modal-dark.png',
  });
  const dialog = await page.getByRole('dialog').count();
  console.log('dialog:', dialog, 'errors:', errors.length, errors[0]?.slice(0, 120) ?? '');
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
