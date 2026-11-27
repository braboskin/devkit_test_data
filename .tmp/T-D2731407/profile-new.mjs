import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const OUT = 'X:/devkit_projects/projects/atlas/.tmp/T-D2731407/out';
const CONTEXT = {
  name: 'Михаил',
  age: '34',
  city: 'Москва',
  profession: 'продуктовый дизайнер',
};
const MOCKS = {
  '/api/me': {
    id: 'u1',
    username: 'mihail',
    display_name: 'Михаил',
    is_owner: true,
  },
  '/api/profile': {
    data: {
      onboarding_done: true,
      ui: { background_ref: 'demo' },
      context: CONTEXT,
      preferences: { about: 'Ценю спокойствие и ясность.' },
    },
    summary:
      'Сферы: Здоровье, Работа; Проекты: Atlas; Цели: Запустить v1; Привычки: сон 7–8 часов',
    updated_at: null,
  },
  '/api/settings/llm': {
    configured: true,
    base_url: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
    masked: 'sk-…9f2c',
  },
  '/api/settings/yadisk': { configured: true, masked: 'y0_…5d1a' },
  '/api/settings/yadisk/config': { oauth_configured: true },
  '/api/settings/notifications': {
    reminders: true,
    quiet_start: '22:00',
    quiet_end: '08:00',
    max_push_per_day: 10,
  },
  '/api/settings/push-subscription': {
    enabled: true,
    subscribed: false,
    public_key: 'BExampleVapid',
  },
  '/api/notifications': { items: [], unread_count: 0 },
};

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1.5,
});
await context.addInitScript(() => {
  window.localStorage.setItem(
    'atlas.theme',
    JSON.stringify({
      mode: 'dark',
      accent: '#334155',
      effects: true,
      background: 'none',
    }),
  );
});
const page = await context.newPage();
page.on('pageerror', (error) => console.log('pageerror:', error.message));
await page.route('**/*', async (route) => {
  const url = new URL(route.request().url());
  if (!url.pathname.startsWith('/api/')) {
    await route.fallback();
    return;
  }
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(MOCKS[url.pathname] ?? []),
  });
});

await page.goto('http://localhost:5174/profile');
await page.getByText('Контекст для агента').first().waitFor({ timeout: 15000 });
await page.waitForTimeout(500);
mkdirSync(OUT, { recursive: true });

const report = await page.evaluate((values) => {
  const headingOf = (section) => section.querySelector('h2')?.textContent.trim();
  const sections = [...document.querySelectorAll('section.panel')];
  const account = sections.find((s) => s.querySelector('label[for="avatar-file"]'));
  const form = [...document.querySelectorAll('form')].find((f) =>
    f.textContent.includes('Контекст для агента'),
  );
  const background = sections.find((s) => headingOf(s) === 'Фон страницы');
  const appearance = sections.find((s) => headingOf(s) === 'Внешний вид');
  const nav = document.querySelector('nav[aria-label="Разделы профиля"]');
  if (!account || !form || !background || !appearance) {
    return { ok: false, reason: 'sections not found' };
  }

  // 1. Поля из «Контекста для агента» — в карточку аккаунта, сетка 2×2.
  const row = form.querySelector('.row');
  const button = form.querySelector('button[type="submit"]');
  Object.assign(row.style, {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '16px',
    width: '100%',
    marginTop: '18px',
    paddingTop: '18px',
    borderTop: '1px solid var(--border)',
  });
  for (const field of row.querySelectorAll('div')) {
    const input = field.querySelector('input');
    if (!input) continue;
    const name = input.getAttribute('name');
    if (name && values[name] !== undefined) input.value = values[name];
  }
  const hint = document.createElement('p');
  hint.className = 'muted';
  hint.textContent =
    'Агенты обращаются по имени и учитывают возраст, город и профессию. Передаётся всем агентам.';
  account.append(row, hint, button);
  form.remove();

  // 2. Своя картинка фона — в блок «Фон» секции «Внешний вид».
  const backgroundRow = background.querySelector('.row');
  const backgroundNote = document.createElement('p');
  backgroundNote.className = 'muted';
  backgroundNote.textContent =
    'Своя картинка затемняется автоматически; пресеты — выше.';
  const fontHeading = [...appearance.querySelectorAll('h2')].find(
    (node) => node.textContent.trim() === 'Фон',
  );
  if (!fontHeading) return { ok: false, reason: 'background group not found' };
  const backgroundBlock = fontHeading.parentElement;
  backgroundBlock.append(backgroundNote, backgroundRow);
  background.remove();

  // 3. Нижняя навигация дублирует меню аватара в топбаре.
  nav?.remove();

  return { ok: true };
}, CONTEXT);
console.log('mutation', JSON.stringify(report));

await page.waitForTimeout(500);
await page.screenshot({ path: `${OUT}/profile-new.png`, fullPage: true });
await context.close();
await browser.close();
