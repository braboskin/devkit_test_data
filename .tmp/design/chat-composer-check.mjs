import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/web/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил', avatar_ref: null },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/agents': [
    { id: 1, name: 'Универсальный помощник', model: 'deepseek-chat', use_critic: false },
  ],
  '/api/chats': [
    { id: 1, agent_id: 1, agent_name: 'Ассистент', title: 'Композер: проверка', created_at: '2026-11-27T10:00:00', updated_at: '2026-11-27T10:00:00' },
    { id: 2, agent_id: 1, agent_name: 'Ассистент', title: 'Итоги недели', created_at: '2026-11-26T10:00:00', updated_at: '2026-11-26T10:00:00' },
  ],
  '/api/chats/1/messages': [
    { id: 1, role: 'user', content: 'Собери план на неделю.', citations: [], status: 'complete', created_at: '2026-11-27T10:00:00Z' },
    { id: 2, role: 'assistant', content: 'Готово: три задачи в фокусе.', citations: [], status: 'complete', created_at: '2026-11-27T10:00:20Z' },
  ],
  '/api/agent-calls': [],
  '/api/proposals': [],
  '/api/settings/llm': { configured: true, base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', masked: 'sk-…7f3a' },
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
  page.on('pageerror', (error) => console.log('pageerror:', String(error)));
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
  await page.waitForTimeout(700);

  const newChat = page.getByRole('button', { name: 'Новый чат' });
  const newChatBox = await newChat.boundingBox();
  console.log('new chat visible:', await newChat.isVisible(), 'width:', newChatBox?.width);

  const attach = page.getByRole('button', { name: 'Прикрепить файлы' });
  console.log('attach visible:', await attach.isVisible());
  const deep = page.getByRole('button', { name: 'Глубокий анализ' });
  console.log('deep pill visible:', await deep.isVisible(), 'pressed:', await deep.getAttribute('aria-pressed'));
  const send = page.getByRole('button', { name: 'Отправить' });
  const sendBox = await send.boundingBox();
  console.log('send visible:', await send.isVisible(), 'round:', sendBox?.width === sendBox?.height, sendBox?.width);
  await send.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/chat-composer-dark.png',
  });
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
