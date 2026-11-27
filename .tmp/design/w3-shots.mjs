import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 2 },
  '/api/chats': [
    { id: 1, title: 'Прототип чата с агентом', updated_at: '2026-11-27T12:04:00Z' },
    { id: 2, title: 'Разбор входящих документов', updated_at: '2026-11-27T11:40:00Z' },
    { id: 3, title: 'Итоги недели', updated_at: '2026-11-26T19:00:00Z' },
  ],
  '/api/chats/1/messages': [
    {
      id: 1,
      role: 'user',
      content: 'Собери каркас чата: список диалогов, тред и композер.',
      citations: [],
      status: 'complete',
      created_at: '2026-11-27T12:04:00Z',
    },
    {
      id: 2,
      role: 'assistant',
      content:
        'Готово. Слева — список диалогов и выбор агента, в центре — лента сообщений, снизу — композер.',
      citations: [],
      status: 'complete',
      created_at: '2026-11-27T12:04:20Z',
    },
  ],
  '/api/agents': [{ id: 1, name: 'Универсальный помощник', model: 'deepseek-chat' }],
};

async function main() {
  const browser = await chromium.launch();
  for (const theme of ['dark', 'light']) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
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
      const body = MOCKS[pathname];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body ?? []),
      });
    });
    await page.goto('http://localhost:5173/chat', { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/w3-chat-${theme}.png`,
    });
    await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/w3-home-${theme}.png`,
    });
    console.log('ok', theme);
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
