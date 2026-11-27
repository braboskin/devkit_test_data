import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/agents': [
    { id: 1, name: 'Библиотекарь', model: 'deepseek-chat', use_critic: false, use_editor: false },
  ],
  '/api/chats': [{ id: 1, title: 'Разбор документов', agent_id: 1, agent_name: 'Библиотекарь' }],
  '/api/proposals?status=pending': [],
  '/api/chats/1/messages': [
    { id: 1, role: 'user', content: 'Что в документе про Q1?', status: 'complete', citations: [] },
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

async function main() {
  const browser = await chromium.launch();
  for (const theme of ['dark', 'light']) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 950 },
      deviceScaleFactor: 1.5,
    });
    await context.addInitScript((mode) => {
      window.localStorage.setItem(
        'atlas.theme',
        JSON.stringify({ mode, accent: '#334155', effects: true, background: 'none' }),
      );
    }, theme);
    const page = await context.newPage();
    const errors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
    await page.route('**/*', async (route) => {
      const requestUrl = new URL(route.request().url());
      if (!requestUrl.pathname.startsWith('/api/')) return route.fallback();
      const key = requestUrl.pathname + (requestUrl.search || '');
      const body = MOCKS[key] ?? MOCKS[requestUrl.pathname] ?? [];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });
    await page.goto('http://localhost:5173/chat', { waitUntil: 'networkidle' });
    await page.waitForTimeout(700);
    const trace = page.getByText('Трейс сабагентов (1)');
    const traceVisible = await trace.first().isVisible().catch(() => false);
    await trace.first().click().catch(() => undefined);
    await page.waitForTimeout(300);
    const traceBody = await page.getByText('Критик → Библиотекарь').isVisible().catch(() => false);
    const gear = await page.getByRole('button', { name: 'Настройки агентов' }).isVisible().catch(() => false);
    const text = await page.locator('body').innerText();
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/ws-h2-chat-after-${theme}.png`,
    });
    console.log(
      theme,
      'errors:', JSON.stringify(errors),
      'gear:', gear,
      'trace:', traceVisible,
      'traceBody:', traceBody,
      'okText:', text.includes('Отправить'),
    );
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
