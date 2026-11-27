const { createRequire } = require('node:module');
const requireWeb = createRequire('X:/devkit_projects/projects/atlas/repo/atlas/web/package.json');
const { chromium } = requireWeb('@playwright/test');

const DOCUMENTS = [
  { id: 5, title: 'Стратегия Atlas на Q1' },
  { id: 6, title: 'Заметки встречи' },
];

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.route(
    (url) => url.pathname.startsWith('/api/'),
    async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      const method = route.request().method();
      if (path === '/api/me') return route.fulfill({ json: { id: 1, username: 'demo', is_owner: true } });
      if (path === '/api/profile') return route.fulfill({ json: { data: { onboarding_done: true }, summary: null, updated_at: null } });
      if (path === '/api/notifications') return route.fulfill({ json: { items: [], unread_count: 0 } });
      if (path === '/api/settings/llm') return route.fulfill({ json: { configured: true, base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', masked: 'sk-…7f3a' } });
      if (path === '/api/agents') return route.fulfill({ json: [{ id: 1, name: 'Ассистент', model: 'deepseek-chat', use_critic: false, use_editor: false }] });
      if (path === '/api/chats') return route.fulfill({ json: [{ id: 1, agent_id: 1, agent_name: 'Ассистент', title: 'Прототип чата с агентом', created_at: '2026-11-27T10:00:00', updated_at: '2026-11-27T10:00:00' }] });
      if (/^\/api\/chats\/\d+\/messages$/.test(path)) return route.fulfill({ json: [] });
      if (path === '/api/agent-calls' || path === '/api/proposals') return route.fulfill({ json: [] });
      if (path === '/api/documents') return route.fulfill({ json: DOCUMENTS });
      return route.fulfill({ json: {} });
    },
  );

  await page.goto('http://127.0.0.1:4173/chat');
  await page.waitForTimeout(800);

  console.log('attach buttons:', await page.getByRole('button', { name: 'Прикрепить документы' }).count());
  await page.getByRole('button', { name: 'Прикрепить документы' }).click();
  await page.waitForTimeout(300);
  console.log('docs panel select count:', await page.getByLabel('Документы для контекста').count());

  await page.getByLabel('Документы для контекста').click();
  await page.waitForTimeout(600);
  console.log('dropdowns:', await page.locator('.ant-select-dropdown').count());
  console.log('options class:', await page.locator('.ant-select-item-option').count());
  console.log('roles option:', await page.getByRole('option').count());
  const html = await page.locator('body').innerHTML();
  const idx = html.indexOf('Стратегия');
  console.log('has text in html:', idx >= 0);
  if (idx >= 0) {
    console.log(html.slice(Math.max(0, idx - 300), idx + 120).replace(/\s+/g, ' '));
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
