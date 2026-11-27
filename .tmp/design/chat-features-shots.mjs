import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/web/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил', avatar_ref: null },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/agents': [{ id: 1, name: 'Универсальный помощник', model: 'deepseek-chat' }],
  '/api/chats': [
    { id: 1, title: 'Ёлка и ёж: разбор', updated_at: '2026-11-27T12:04:00Z' },
    { id: 2, title: 'Разбор входящих документов', updated_at: '2026-11-27T11:40:00Z' },
    { id: 3, title: 'Итоги недели', updated_at: '2026-11-26T19:00:00Z' },
  ],
  '/api/chats/1/messages': [
    {
      id: 1,
      role: 'user',
      content: 'Собери план на неделю по проекту Atlas.',
      citations: [],
      status: 'complete',
      created_at: '2026-11-27T12:04:00Z',
    },
    {
      id: 2,
      role: 'assistant',
      content:
        'Собрал: три задачи в фокусе, одна привычка под угрозой. Приложил документ «Стратегия Q1» — в нём детали.',
      citations: [],
      status: 'complete',
      created_at: '2026-11-27T12:04:20Z',
      meta: { deep: true },
    },
  ],
  '/api/documents': [
    { id: 5, title: 'Стратегия Atlas на Q1' },
    { id: 6, title: 'Заметки встречи с командой' },
    { id: 7, title: 'Черновик статьи' },
  ],
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

  await page.goto('http://localhost:5173/chat', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/chat-features-default-dark.png',
  });

  const search = page.getByLabel('Поиск по диалогам');
  if (await search.count()) {
    await search.fill('ёлка');
    await page.waitForTimeout(400);
    await page.screenshot({
      path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/chat-features-search-dark.png',
    });
  }

  const attach = page.getByLabel('Прикрепить документы');
  if (await attach.count()) {
    await attach.click();
    await page.waitForTimeout(500);
    await page.screenshot({
      path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/chat-features-attachments-dark.png',
    });
  }
  console.log('ok');
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
