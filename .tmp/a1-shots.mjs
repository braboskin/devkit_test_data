import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/web/package.json',
);
const { chromium } = require('@playwright/test');

const BASE = 'http://127.0.0.1:4173';

const MOCKS = {
  '/api/me': { id: 'u1', username: 'demo', is_owner: true },
  '/api/profile': {
    data: { onboarding_done: true },
    summary: null,
    updated_at: null,
  },
  '/api/notifications': { items: [], unread_count: 2 },
  '/api/spheres': [
    { id: 1, name: 'Здоровье', color: '#22c55e', description: null },
    { id: 2, name: 'Работа', color: '#3b82f6', description: null },
  ],
  '/api/projects': [
    {
      id: 1,
      name: 'Атлас',
      sphere_id: 2,
      status: 'active',
      due_at: '2026-12-15',
    },
  ],
  '/api/events': [
    {
      id: 1,
      title: 'Планёрка',
      start_at: '2026-11-28T15:00:00',
      end_at: '2026-11-28T16:00:00',
      all_day: false,
    },
  ],
  '/api/tasks': [],
  '/api/documents': [],
  '/api/chats': [],
  '/api/agents': [],
  '/api/proposals?status=pending': [],
  '/api/jobs': [],
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
  '/api/settings/yadisk': { configured: false, masked: null },
  '/api/settings/yadisk/config': { oauth_configured: false },
  '/api/settings/notifications': {
    reminders: true,
    quiet_start: null,
    quiet_end: null,
    max_push: 10,
  },
  '/api/settings/push-subscription': { configured: false },
};

async function shot(browser, { theme, width, height, path, url }) {
  const context = await browser.newContext({
    viewport: { width, height },
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
  const errors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  await page.route(
    (u) => u.pathname.startsWith('/api/'),
    async (route) => {
      const requestUrl = new URL(route.request().url());
      const key = requestUrl.pathname + (requestUrl.search || '');
      const body = MOCKS[key] ?? MOCKS[requestUrl.pathname] ?? [];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    },
  );
  await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.screenshot({ path });
  console.log(path, 'errors:', JSON.stringify(errors));
  await context.close();
}

async function main() {
  const browser = await chromium.launch();
  const out = 'X:/devkit_projects/projects/atlas/.tmp/design/out';
  await shot(browser, {
    theme: 'dark',
    width: 1440,
    height: 950,
    path: `${out}/a1-shell-dark.png`,
    url: '/calendar',
  });
  await shot(browser, {
    theme: 'light',
    width: 1440,
    height: 950,
    path: `${out}/a1-shell-light.png`,
    url: '/calendar',
  });
  await shot(browser, {
    theme: 'dark',
    width: 390,
    height: 844,
    path: `${out}/a1-shell-mobile-dark.png`,
    url: '/calendar',
  });
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
