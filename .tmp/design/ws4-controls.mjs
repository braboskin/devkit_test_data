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
  '/api/projects': [{ id: 1, name: 'Atlas', status: 'active' }],
  '/api/spheres': [{ id: 1, name: 'Работа', color: '#3b82f6' }],
  '/api/tasks': [],
  '/api/people': [],
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
  await page.goto('http://localhost:5199/tasks', { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);

  const height = async (selector) => {
    const locator = page.locator(selector).first();
    if ((await locator.count()) === 0) {
      return null;
    }
    try {
      const box = await locator.boundingBox({ timeout: 2000 });
      return box ? Math.round(box.height) : null;
    } catch {
      return null;
    }
  };

  const input = await height('form .ant-input');
  const textarea = await height('form textarea.ant-input');
  const button = await height('form .ant-btn');
  const picker = await height('form .ant-picker');
  const selectClosed = await height('form .ant-select');
  console.log('input:', input, 'textarea:', textarea, 'button:', button, 'picker:', picker, 'select:', selectClosed);

  const select = page.locator('form .ant-select').first();
  await select.click();
  await page.waitForTimeout(250);
  const selectOpen = await height('form .ant-select');
  const option = page.locator('.ant-select-dropdown:visible .ant-select-item-option').first();
  if (await option.count()) {
    await option.click();
    await page.waitForTimeout(250);
  }
  const selectChosen = await height('form .ant-select');
  console.log('select open:', selectOpen, 'chosen:', selectChosen);

  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/ws4-controls-dark.png',
  });
  await browser.close();

  const heights = [input, button, picker, selectClosed, selectOpen, selectChosen];
  const jump = new Set(heights.filter((value) => value !== null));
  console.log('distinct heights:', [...jump].join(','));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
