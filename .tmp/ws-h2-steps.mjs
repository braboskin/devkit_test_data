import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: {}, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/settings/llm': { configured: false },
  '/api/settings/llm/models': {
    models: ['deepseek-chat', 'deepseek-reasoner'],
    detail: null,
  },
  '/api/settings/yadisk': { configured: false },
  '/api/settings/yadisk/config': { oauth_configured: true },
  '/api/spheres': [],
};

async function probe(route, shot, checks) {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    deviceScaleFactor: 1.5,
  });
  await context.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({ mode: 'dark', accent: '#334155', effects: true, background: 'none' }),
    );
    window.localStorage.removeItem('atlas.onboarding.v2');
  });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  await page.route('**/*', async (requestRoute) => {
    const requestUrl = new URL(requestRoute.request().url());
    if (!requestUrl.pathname.startsWith('/api/')) return requestRoute.fallback();
    const body = MOCKS[requestUrl.pathname] ?? [];
    await requestRoute.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
  await page.goto(`http://localhost:5173${route}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(700);
  const text = await page.locator('body').innerText();
  await page.screenshot({ path: shot });
  console.log(route, 'errors:', JSON.stringify(errors), checks.map((label) => `${label}=${text.includes(label)}`).join(' '));
  await browser.close();
}

async function main() {
  await probe('/setup/model', 'X:/devkit_projects/projects/atlas/.tmp/ws-h2-model-dark.png', [
    'Подключение модели',
    'Провайдер',
    'API-ключ',
    'Модель',
  ]);
  await probe('/survey?step=1', 'X:/devkit_projects/projects/atlas/.tmp/ws-h2-spheres-dark.png', [
    'Сферы жизни',
    'Создадим',
    'здоровье',
    'Утвердить',
  ]);
  await probe('/survey?step=3', 'X:/devkit_projects/projects/atlas/.tmp/ws-h2-rhythm-dark.png', [
    'Метрики',
    'Привычки',
  ]);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
