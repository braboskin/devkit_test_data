import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/agents': [
    {
      id: 1,
      kind: 'preset',
      name: 'Универсальный помощник',
      role: 'Отвечает на вопросы по вашим данным',
      instructions: 'Отвечай кратко.',
      allowed_spheres: [],
      allowed_projects: [],
      tools: [],
      model: 'deepseek-chat',
      temperature: 0.7,
      use_critic: true,
      use_editor: false,
      journal_access: false,
      safety_note: null,
    },
  ],
  '/api/agents/tools': [
    { name: 'search', description: 'Поиск по документам' },
    { name: 'tasks', description: 'Задачи' },
  ],
  '/api/spheres': [{ id: 1, name: 'Здоровье', color: '#34d399', description: null }],
  '/api/projects': [{ id: 1, name: 'Atlas', sphere_id: 1, status: 'active' }],
  '/api/jobs': [
    {
      id: 1,
      type: 'extract',
      status: 'running',
      payload: { document_id: 1 },
      attempts: 0,
      created_at: '2026-11-27T20:00:00Z',
      started_at: '2026-11-27T20:00:05Z',
      finished_at: null,
      error: null,
    },
    {
      id: 2,
      type: 'extract',
      status: 'done',
      payload: { document_id: 2 },
      attempts: 1,
      created_at: '2026-11-27T19:00:00Z',
      started_at: '2026-11-27T19:00:05Z',
      finished_at: '2026-11-27T19:01:00Z',
      error: null,
    },
  ],
  '/api/documents': [
    { id: 1, title: 'Договор аренды.pdf' },
    { id: 2, title: 'Заметки по проекту.md' },
  ],
  '/api/settings/worker-token': {
    configured: true,
    created_at: '2026-11-20T10:00:00Z',
    last_seen_at: '2026-11-27T21:55:00Z'
  },
  '/api/notifications': {
    items: [
      {
        id: 1,
        kind: 'reminder',
        title: 'Напоминание: планёрка',
        body: 'Сегодня в 10:00 — короткая планёрка по проекту Atlas.',
        link: '/calendar',
        read_at: null,
        created_at: '2026-11-27T07:00:00Z',
      },
      {
        id: 2,
        kind: 'review',
        title: 'Обзор недели готов',
        body: 'Собрано 12 задач и 3 события.',
        link: null,
        read_at: '2026-11-26T21:00:00Z',
        created_at: '2026-11-26T20:00:00Z',
      },
    ],
    unread_count: 1,
  },
};

const SEARCH_GROUPS = {
  q: 'атлас',
  groups: [
    {
      type: 'projects',
      total: 1,
      items: [
        {
          id: 1,
          title: 'Atlas',
          status: 'active',
          snippet: 'Проект Atlas — центр жизни',
        },
      ],
    },
    {
      type: 'documents',
      total: 1,
      items: [
        {
          id: 1,
          title: 'Договор аренды.pdf',
          snippet: 'атлас документы аренды',
        },
      ],
    },
  ],
};

const SEARCH_HITS = [
  {
    chunk_id: 1,
    document_id: 1,
    title: 'Договор аренды.pdf',
    text: 'Атлас — документы аренды',
  },
];

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1.5,
  });
  await context.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({ mode: 'dark', accent: '#334155', effects: true, background: 'none' }),
    );
  });
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/api/')) {
      await route.fallback();
      return;
    }
    if (url.pathname === '/api/search') {
      const scoped = url.searchParams.get('scope') === 'all';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(scoped ? SEARCH_GROUPS : SEARCH_HITS),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCKS[url.pathname] ?? []),
    });
  });

  for (const [name, path] of [
    ['agents', '/settings/agents'],
    ['notifications', '/notifications'],
    ['jobs', '/jobs'],
    ['search', '/search'],
    ['space', '/space'],
  ]) {
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    await page.goto(`http://localhost:5174${path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(700);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/ws-f2-${name}-dark.png`,
    });
    console.log(name, 'errors:', errors.length, errors[0]?.slice(0, 120) ?? '');
    page.removeAllListeners('pageerror');
  }

  // Оверлей поиска: открыть с Space, отправить запрос, проверить статус и результат.
  const overlayErrors = [];
  page.on('pageerror', (error) => overlayErrors.push(String(error)));
  await page.goto('http://localhost:5174/space', { waitUntil: 'networkidle' });
  await page.waitForTimeout(700);
  await page.getByRole('button', { name: /Поиск по Atlas/ }).click();
  await page.waitForTimeout(400);
  const modalOpen = await page.locator('.ant-modal').count();
  await page.getByLabel('Поисковый запрос').fill('атлас');
  await page.getByRole('button', { name: 'Найти' }).click();
  await page.waitForTimeout(700);
  const results = await page.getByRole('link', { name: /Договор аренды/ }).count();
  const status = await page.getByRole('status').last().textContent();
  await page.screenshot({
    path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/ws-f2-overlay-dark.png',
  });
  console.log(
    'overlay',
    JSON.stringify({ modalOpen, results, status, errors: overlayErrors.length }),
  );

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
