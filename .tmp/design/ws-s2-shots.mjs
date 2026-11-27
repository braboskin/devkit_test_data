import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': {
    id: 'u1',
    username: 'Михаил',
    display_name: 'Михаил',
    avatar_ref: null,
  },
  '/api/profile': {
    data: {
      onboarding_done: true,
      context: { name: 'Михаил', age: '34', city: 'Москва', profession: 'PM' },
    },
    summary: null,
    updated_at: null,
  },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/people': [
    {
      id: 1,
      name: 'Анна Петрова',
      tags: ['команда', 'дизайн'],
      contacts: { email: 'anna@example.com' },
      photo_ref: null,
      relation: 'коллега',
      notes: null,
    },
    {
      id: 2,
      name: 'Олег Смирнов',
      tags: ['семья'],
      contacts: {},
      photo_ref: null,
      relation: 'друг',
      notes: null,
    },
  ],
  '/api/people/1/relations': {
    spheres: [],
    projects: [],
    events: [],
    tasks: [],
  },
  '/api/spheres': [],
  '/api/projects': [],
  '/api/goals': [
    {
      id: 1,
      title: 'Прочитать 12 книг',
      status: 'active',
      criteria: 'по одной в месяц',
      current: 4,
      target: 12,
      progress: 0.33,
      due_at: null,
      sphere_id: null,
      project_id: null,
    },
  ],
  '/api/habits': [
    {
      id: 1,
      title: 'Сон 7–8 часов',
      cadence: 'daily',
      target_per_period: 1,
      streak: 4,
      today: true,
    },
    {
      id: 2,
      title: 'Тренировка',
      cadence: 'weekly',
      target_per_period: 3,
      streak: 2,
      today: false,
    },
  ],
  '/api/metrics': [
    { id: 1, name: 'Вес', kind: 'number', unit: 'кг', cadence: 'daily' },
  ],
  '/api/metrics/1/entries': {
    points: [
      { ts: '2026-11-24T08:00:00', value: 81.2 },
      { ts: '2026-11-25T08:00:00', value: 80.9 },
      { ts: '2026-11-26T08:00:00', value: 80.4 },
    ],
    avg: 80.8,
    previous: null,
  },
  '/api/journal': [
    {
      id: 1,
      date: '2026-11-26T21:00:00',
      topic: 'день',
      content: 'Спокойный день, закрыл два блока задач.',
    },
  ],
  '/api/journal/topics': [{ topic: 'день', count: 1 }],
  '/api/reviews': [
    {
      id: 1,
      kind: 'review.daily',
      period_start: '2026-11-26T00:00:00',
      period_end: '2026-11-26T23:59:59',
      summary: 'Фокус держался, вечер свободен.',
      recommendations: ['Вода'],
    },
  ],
  '/api/growth/settings': {
    daily_enabled: true,
    daily_at: '08:00',
    weekly_enabled: true,
    weekly_day: 0,
    weekly_at: '09:00',
    triage_enabled: true,
    audit_enabled: false,
    nudge_enabled: true,
  },
};

async function main() {
  const browser = await chromium.launch();
  for (const theme of ['dark', 'light']) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
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
    page.on('pageerror', (error) => errors.push(String(error)));
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
    for (const [name, path] of [
      ['people', '/people'],
      ['profile', '/profile'],
      ['growth', '/growth'],
    ]) {
      await page.goto(`http://localhost:5173${path}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(900);
      await page.screenshot({
        path: `X:/devkit_projects/projects/atlas/.tmp/design/out/ws-s2-${name}-${theme}.png`,
      });
    }
    if (theme === 'dark') {
      await page.goto('http://localhost:5173/growth', { waitUntil: 'networkidle' });
      await page.getByRole('tab', { name: 'Привычки' }).click();
      await page.waitForTimeout(500);
      await page.screenshot({
        path: 'X:/devkit_projects/projects/atlas/.tmp/design/out/ws-s2-growth-habits-dark.png',
      });
    }
    console.log(theme, 'errors:', errors.length, errors[0]?.slice(0, 160) ?? '');
    await context.close();
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
