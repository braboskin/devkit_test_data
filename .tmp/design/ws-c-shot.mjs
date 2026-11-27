import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const OUT = path.resolve('.tmp/design/out');

const TOKENS = `
:root, html[data-theme='dark'] {
  --bg0: #07080a;
  --bg1: #171a20;
  --surface: rgba(24, 27, 33, .52);
  --raised: rgba(30, 34, 41, .80);
  --menu-bg: rgba(26, 30, 36, .97);
  --sunken: rgba(9, 10, 12, .88);
  --hover: rgba(255, 255, 255, .05);
  --text: #eef1f5;
  --muted: #a4abb6;
  --faint: #7d858f;
  --border: rgba(255, 255, 255, .085);
  --border-strong: rgba(255, 255, 255, .14);
  --ok: #34d399;
  --warn: #fbbf24;
  --danger: #f87171;
  --shadow: 0 24px 60px -28px rgba(0, 0, 0, .9);
  --blur: 30px;
  --blur-raised: 40px;
  --bg-image: none;
  --bg-scrim: rgba(7, 8, 10, .5);
  color-scheme: dark;
}
html[data-theme='light'] {
  --bg0: #f7f8fa;
  --bg1: #e7ebf1;
  --surface: rgba(255, 255, 255, .62);
  --raised: rgba(255, 255, 255, .90);
  --menu-bg: rgba(255, 255, 255, .985);
  --sunken: rgba(255, 255, 255, .95);
  --hover: rgba(15, 23, 42, .05);
  --text: #12161c;
  --muted: #4b5563;
  --faint: #6b7280;
  --border: rgba(15, 23, 42, .10);
  --border-strong: rgba(15, 23, 42, .18);
  --ok: #047857;
  --warn: #b45309;
  --danger: #b91c1c;
  --shadow: 0 20px 44px -28px rgba(15, 23, 42, .38);
  color-scheme: light;
}
body {
  background: var(--bg0) !important;
  color: var(--text);
}
`;

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': {
    data: { onboarding_done: true },
    summary: null,
    updated_at: null,
  },
  '/api/notifications': { items: [], unread_count: 3 },
  '/api/settings/notifications': {
    reminders: true,
    quiet_start: null,
    quiet_end: null,
    max_push_per_day: 10,
  },
  '/api/settings/llm': { configured: false },
  '/api/chats': [],
  '/api/documents': [],
};

async function mockApi(page) {
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
}

async function shot(browser, name, theme, viewport) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1.5,
  });
  await context.addInitScript(
    (value) => {
      window.localStorage.setItem('atlas.theme', JSON.stringify(value));
    },
    { mode: theme, accent: '#334155', effects: true, background: 'none' },
  );
  const page = await context.newPage();
  await mockApi(page);
  await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded' });
  await page.addStyleTag({ content: TOKENS });
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, name) });
  await context.close();
  console.log('ok', name);
}

async function main() {
  const browser = await chromium.launch();

  await shot(browser, 'ws-c-shell-dark.png', 'dark', {
    width: 1440,
    height: 900,
  });
  await shot(browser, 'ws-c-shell-light.png', 'light', {
    width: 1440,
    height: 900,
  });

  const context = await browser.newContext({
    viewport: { width: 430, height: 900 },
    deviceScaleFactor: 1.5,
  });
  await context.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({
        mode: 'dark',
        accent: '#334155',
        effects: true,
        background: 'none',
      }),
    );
  });
  const page = await context.newPage();
  await mockApi(page);
  await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded' });
  await page.addStyleTag({ content: TOKENS });
  await page.waitForTimeout(600);
  await page.locator('header > span > button').click();
  await page.waitForTimeout(500);
  await page.screenshot({
    path: path.join(OUT, 'ws-c-shell-mobile-drawer.png'),
  });
  await context.close();
  console.log('ok ws-c-shell-mobile-drawer.png');

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
