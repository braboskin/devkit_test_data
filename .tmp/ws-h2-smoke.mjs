import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const CHAT_MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/agents': [
    { id: 1, name: 'Библиотекарь', model: 'deepseek-chat', use_critic: false, use_editor: false },
  ],
  '/api/chats': [
    { id: 1, title: 'Разбор документов', agent_id: 1, agent_name: 'Библиотекарь' },
    { id: 2, title: 'Итоги недели', agent_id: 1, agent_name: 'Библиотекарь' },
  ],
  '/api/proposals?status=pending': [],
  '/api/chats/1/messages': [
    {
      id: 1,
      role: 'user',
      content: 'Что в документе про Q1?',
      status: 'complete',
      citations: [],
    },
    {
      id: 2,
      role: 'assistant',
      content: 'Три цели: фокус на знаниях, чат с агентом и календарь.',
      status: 'complete',
      citations: [{ document_id: 7, title: 'Стратегия Q1', text: 'Фрагмент про цели' }],
    },
  ],
  '/api/agent-calls?chat_id=1': [
    { id: 1, parent_name: 'Библиотекарь', child_name: 'Критик', output: 'Ок' },
  ],
  '/api/settings/llm': { configured: true, base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', masked: 'sk-…7f3a' },
};

const SETUP_MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: {}, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/settings/llm': { configured: false },
  '/api/settings/yadisk': { configured: false },
  '/api/settings/yadisk/config': { oauth_configured: true },
  '/api/spheres': [],
};

async function probe(page, url, mocks, shot) {
  const errors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url());
    if (!requestUrl.pathname.startsWith('/api/')) return route.fallback();
    const key = requestUrl.pathname + (requestUrl.search || '');
    const body = mocks[key] ?? mocks[requestUrl.pathname] ?? [];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.screenshot({ path: shot });
  return errors;
}

async function main() {
  const browser = await chromium.launch();
  for (const theme of ['dark']) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 950 }, deviceScaleFactor: 1.5 });
    await context.addInitScript((mode) => {
      window.localStorage.setItem('atlas.theme', JSON.stringify({ mode, accent: '#334155', effects: true, background: 'none' }));
    }, theme);

    const chatPage = await context.newPage();
    const chatErrors = await probe(
      chatPage,
      'http://localhost:5173/chat',
      CHAT_MOCKS,
      `X:/devkit_projects/projects/atlas/.tmp/ws-h2-chat-${theme}.png`,
    );
    const chatText = await chatPage.locator('body').innerText();
    console.log('CHAT errors:', JSON.stringify(chatErrors));
    console.log('CHAT has header:', chatText.includes('Чат'), 'has composer:', chatText.includes('Отправить'), 'has trace:', chatText.includes('Трейс сабагентов'));
    await chatPage.close();

    const setupPage = await context.newPage();
    const setupErrors = await probe(
      setupPage,
      'http://localhost:5173/setup',
      SETUP_MOCKS,
      `X:/devkit_projects/projects/atlas/.tmp/ws-h2-setup-${theme}.png`,
    );
    const setupText = await setupPage.locator('body').innerText();
    console.log('SETUP errors:', JSON.stringify(setupErrors));
    console.log('SETUP has welcome:', setupText.includes('Добро пожаловать в Atlas'), 'steps:', setupText.includes('Приветствие'), 'button:', setupText.includes('Начать настройку'));
    await setupPage.close();
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
