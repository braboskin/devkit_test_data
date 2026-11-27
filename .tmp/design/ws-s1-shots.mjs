import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const SPHERES = [
  { id: 1, name: 'Здоровье', color: '#34d399', description: 'Сон, спорт, питание' },
  { id: 2, name: 'Работа', color: '#60a5fa', description: 'Проекты и задачи' },
  { id: 3, name: 'Развитие', color: '#c084fc', description: 'Книги и курсы' },
];

const PROJECTS = [
  { id: 1, name: 'Atlas', sphere_id: 2, status: 'doing', due_at: '2026-12-15T00:00:00Z', description: 'Личная ОС знаний' },
  { id: 2, name: 'Английский', sphere_id: 3, status: 'todo', due_at: null, description: null },
];

const TASKS = [
  { id: 1, title: 'Свести прототип чата', status: 'doing', priority: 'high', due_at: '2026-11-28T10:00:00Z' },
  { id: 2, title: 'Проверить ingestion', status: 'todo', priority: 'medium', due_at: null },
  { id: 3, title: 'Обновить README', status: 'done', priority: 'low', due_at: '2026-11-20T00:00:00Z' },
];

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/spheres': SPHERES,
  '/api/spheres/1': SPHERES[0],
  '/api/spheres/1/summary': { projects: 2, tasks: 7, tasks_done: 3, people: 4, documents: 5 },
  '/api/projects': PROJECTS,
  '/api/projects?sphere_id=1': PROJECTS.filter((p) => p.sphere_id === 1),
  '/api/projects/1': PROJECTS[0],
  '/api/projects/1/summary': { tasks: 7, tasks_done: 4, people: 3, documents: 6 },
  '/api/tasks': TASKS,
  '/api/tasks?sphere_id=1': TASKS,
  '/api/tasks?project_id=1': TASKS,
  '/api/documents': TASKS.map((task) => ({
    id: task.id,
    title: `Документ ${task.id}`,
    status: 'ready',
  })),
  '/api/tasks/1/dependencies': [],
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
      JSON.stringify({ mode: 'dark', accent: '#334155', effects: true, background: 'none' }),
    );
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/api/')) {
      await route.fallback();
      return;
    }
    const key = url.search ? `${url.pathname}${url.search}` : url.pathname;
    const body = MOCKS[key] ?? MOCKS[url.pathname] ?? [];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });

  for (const [name, path] of [
    ['spheres', '/spheres'],
    ['projects', '/projects'],
    ['project', '/projects/1'],
    ['sphere', '/spheres/1'],
  ]) {
    await page.goto(`http://localhost:5173${path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(700);
    await page.screenshot({
      path: `X:/devkit_projects/projects/atlas/.tmp/design/out/ws-s1-${name}-dark.png`,
    });
    console.log(name, 'ok, errors:', errors.length);
  }
  if (errors.length) {
    console.log(errors.slice(0, 3).join('\n'));
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
