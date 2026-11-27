import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': {
    data: { onboarding_done: true, timezone: 'Europe/Moscow' },
    summary: 'Личная операционная система знаний.',
    updated_at: '2026-11-27T10:00:00Z',
  },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/settings/llm': {
    configured: true,
    base_url: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
    masked: 'sk-…7f3a',
  },
  '/api/settings/llm/models': { models: ['deepseek-chat'], detail: null },
  '/api/settings/yadisk': { configured: false, masked: null },
  '/api/settings/yadisk/config': { oauth_configured: false },
  '/api/settings/notifications': {
    reminders: true,
    quiet_start: '23:00',
    quiet_end: '08:00',
    max_push_per_day: 10,
  },
  '/api/settings/push-subscription': {
    enabled: false,
    subscribed: false,
    public_key: null,
  },
};

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const requests = [];
  const errors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') {
      console.log('CONSOLE.ERROR:', message.text().slice(0, 600));
    }
  });
  page.on('pageerror', (error) => {
    errors.push(String(error));
    console.log('PAGEERROR:', error.message);
    console.log('STACK:', error.stack);
  });
  await page.route('**/*', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (!pathname.startsWith('/api/')) {
      await route.fallback();
      return;
    }
    if (request.method() !== 'GET') {
      requests.push({
        method: request.method(),
        pathname,
        body: request.postData() ?? '',
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCKS[pathname] ?? {}),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCKS[pathname] ?? []),
    });
  });

  await page.goto('http://localhost:5173/settings', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  console.log('errors-now:', JSON.stringify(errors));
  console.log('buttons:', JSON.stringify(await page.getByRole('button').allInnerTexts()));
  console.log('headings:', JSON.stringify(await page.getByRole('heading').allInnerTexts()));
  console.log('url:', page.url());

  // 1. Профиль: сохранить JSON и сводку.
  await page.getByRole('button', { name: 'Сохранить профиль' }).click();
  await page.waitForTimeout(400);

  // 2. Ручной токен: раскрыть Collapse, сохранить токен.
  await page.getByText('Вставить токен вручную').click();
  await page.waitForTimeout(300);
  await page.getByLabel('Новый токен Яндекс.Диска').fill('y0-test-token');
  await page.getByRole('button', { name: 'Сохранить токен' }).click();
  await page.waitForTimeout(400);

  // 3. Отключить Яндекс.Диск: OAuth не настроен, кнопки «Отключить» нет,
  //    поэтому проверяем, что предупреждение об OAuth видно.
  const oauthWarning = await page
    .getByText('OAuth на сервере не настроен')
    .isVisible();

  // 4. Невалидный JSON → сообщение об ошибке, запроса нет.
  await page.getByLabel('Данные профиля (JSON, структурированно)').fill('[1,2]');
  const before = requests.length;
  await page.getByRole('button', { name: 'Сохранить профиль' }).click();
  await page.waitForTimeout(300);
  const invalidJsonError = await page
    .getByText('Профиль должен быть JSON-объектом.')
    .isVisible();
  const noRequestOnInvalid = requests.length === before;

  console.log(
    JSON.stringify(
      {
        errors,
        oauthWarning,
        invalidJsonError,
        noRequestOnInvalid,
        requests,
      },
      null,
      2,
    ),
  );
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
