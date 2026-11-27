const { createRequire } = require('node:module');
require('node:module');

const requireWeb = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/web/package.json',
);
const { chromium } = requireWeb('@playwright/test');

const DOCUMENTS = [
  { id: 5, title: 'Стратегия Atlas на Q1' },
  { id: 6, title: 'Заметки встречи' },
];

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.addInitScript(() => {
    const chatState = { bodies: [], cancels: 0 };
    window.__chat = chatState;
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const request = input instanceof Request ? input : null;
      const url = request ? request.url : String(input);
      const method = (init && init.method) ?? request?.method ?? 'GET';
      if (url.includes('/messages/') && url.endsWith('/cancel')) {
        chatState.cancels += 1;
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      if (url.endsWith('/api/chats/1/messages') && method === 'POST') {
        chatState.bodies.push(JSON.parse(String(init?.body ?? '{}')));
        return new Response(
          'data: {"type":"start","message_id":42,"meta":{"deep":true}}\n\ndata: {"type":"done"}\n\n',
          { status: 200, headers: { 'content-type': 'text/event-stream' } },
        );
      }
      return original(input, init);
    };
  });

  await page.route(
    (url) => url.pathname.startsWith('/api/'),
    async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/api/me')
        return route.fulfill({ json: { id: 1, username: 'demo', is_owner: true } });
      if (path === '/api/profile')
        return route.fulfill({
          json: { data: { onboarding_done: true }, summary: null, updated_at: null },
        });
      if (path === '/api/notifications')
        return route.fulfill({ json: { items: [], unread_count: 0 } });
      if (path === '/api/settings/llm')
        return route.fulfill({
          json: { configured: true, base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', masked: 'sk-x' },
        });
      if (path === '/api/agents')
        return route.fulfill({
          json: [{ id: 1, name: 'Ассистент', model: 'deepseek-chat', use_critic: false, use_editor: false }],
        });
      if (path === '/api/chats')
        return route.fulfill({
          json: [{ id: 1, agent_id: 1, agent_name: 'Ассистент', title: 'Прототип чата с агентом', created_at: '2026-11-27T10:00:00', updated_at: '2026-11-27T10:00:00' }],
        });
      if (/^\/api\/chats\/\d+\/messages$/.test(path)) return route.fulfill({ json: [] });
      if (path === '/api/agent-calls' || path === '/api/proposals') return route.fulfill({ json: [] });
      if (path === '/api/documents') return route.fulfill({ json: DOCUMENTS });
      return route.fulfill({ json: {} });
    },
  );

  await page.goto('http://127.0.0.1:4173/chat');
  await page.waitForTimeout(700);
  await page.getByLabel('Сообщение').fill('Что по стратегии?');
  console.log('filled message');
  await page.getByRole('button', { name: 'Прикрепить документы' }).click();
  console.log('opened attach');
  await page.getByLabel('Документы для контекста').click();
  await page.waitForTimeout(400);
  const options = page.locator('.ant-select-dropdown .ant-select-item-option');
  console.log('options:', await options.count());
  await options.filter({ hasText: 'Стратегия Atlas на Q1' }).click();
  console.log('clicked option');
  await page.waitForTimeout(400);
  console.log(
    'remove buttons:',
    await page.getByRole('button', { name: /Убрать/ }).count(),
    'names:',
    await page.getByRole('button', { name: /Убрать/ }).allTextContents(),
  );
  console.log('switch count:', await page.getByRole('switch', { name: 'Глубокий анализ' }).count());
  await page.getByRole('switch', { name: 'Глубокий анализ' }).click();
  console.log('switch clicked');
  await page.getByRole('button', { name: 'Отправить' }).click();
  console.log('send clicked');
  await page.waitForTimeout(1200);
  console.log('bodies:', JSON.stringify(await page.evaluate(() => window.__chat.bodies)));
  console.log('messages text:', (await page.getByLabel('Лента сообщений').innerText()).slice(0, 200));
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
