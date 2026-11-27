import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': {
    data: { onboarding_done: true },
    summary: null,
    updated_at: null,
  },
  '/api/notifications': { items: [], unread_count: 0 },
};

async function open(browser, prefs) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript((value) => {
    window.localStorage.setItem('atlas.theme', JSON.stringify(value));
  }, prefs);
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
  await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(700);
  return { context, page };
}

async function main() {
  const browser = await chromium.launch();

  // 1. Анимация экрана включена по умолчанию.
  const on = await open(browser, {
    mode: 'dark',
    accent: '#334155',
    effects: true,
    background: 'none',
  });
  const animOn = await on.page.evaluate(() => {
    const el = document.querySelector('main#main > div');
    return el ? getComputedStyle(el).animationName : 'no-element';
  });
  console.log('animation effects=on:', animOn);
  await on.context.close();

  // 2. data-effects="off" отключает анимацию.
  const off = await open(browser, {
    mode: 'dark',
    accent: '#334155',
    effects: false,
    background: 'none',
  });
  const animOff = await off.page.evaluate(() => {
    const el = document.querySelector('main#main > div');
    return el ? getComputedStyle(el).animationName : 'no-element';
  });
  console.log('animation effects=off:', animOff);

  // 3. Мобильный drawer: фон панели непрозрачный после правки styles.
  await off.context.close();
  const mobile = await browser.newContext({
    viewport: { width: 430, height: 900 },
    deviceScaleFactor: 1.5,
  });
  await mobile.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({ mode: 'dark', accent: '#334155', effects: true, background: 'none' }),
    );
  });
  const page = await mobile.newPage();
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
  await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(600);
  await page.locator('header > span > button').click();
  await page.waitForTimeout(400);
  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/ws-c-shell-mobile-drawer.png',
  });
  await mobile.close();
  console.log('mobile drawer screenshot updated');

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
