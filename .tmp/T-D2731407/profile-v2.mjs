import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const OUT = 'X:/devkit_projects/projects/atlas/.tmp/T-D2731407/out';
const FIELDS = [
  ['login', 'Логин', 'text', 'mihail'],
  ['password', 'Пароль', 'password', ''],
  ['firstName', 'Имя', 'text', 'Михаил'],
  ['lastName', 'Фамилия', 'text', 'Иванов'],
  ['city', 'Город', 'text', 'Москва'],
  ['age', 'Возраст', 'text', '34'],
  ['occupation', 'Род деятельности', 'text', 'продуктовый дизайнер'],
];
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
      preferences: { about: 'Ценю спокойствие и ясность.' },
    },
    summary: 'Сферы: Здоровье, Работа; Проекты: Atlas',
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

const report = await page.evaluate(
  ({ fields }) => {
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

    // --- 1. Карточка профиля: аватар слева, поля справа ---
    const row = account.querySelector('.row');
    const avatar = row.children[0];
    const stack = row.children[1];
    const fieldSource = form.querySelector('.field');

    Object.assign(row.style, {
      display: 'grid',
      gridTemplateColumns: '220px 1fr',
      alignItems: 'start',
      gap: '36px',
      width: '100%',
    });

    // Аватар: клик = загрузка, красный крестик при наличии фото.
    avatar.style.position = 'relative';
    avatar.style.cursor = 'pointer';
    avatar.style.paddingTop = '6px';
    const picture = avatar.querySelector('.ant-avatar');
    if (picture) {
      picture.style.width = '96px';
      picture.style.height = '96px';
      picture.style.lineHeight = '96px';
      picture.style.fontSize = '34px';
      picture.style.borderRadius = '50%';
    }
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.setAttribute('aria-label', 'Удалить фото');
    removeButton.textContent = '×';
    Object.assign(removeButton.style, {
      position: 'absolute',
      top: '0',
      left: '72px',
      width: '26px',
      height: '26px',
      padding: '0',
      border: '2px solid var(--surface)',
      borderRadius: '50%',
      background: '#e5484d',
      color: '#fff',
      fontSize: '16px',
      lineHeight: '22px',
      cursor: 'pointer',
    });
    avatar.append(removeButton);

    // Поля профиля — одним столбцом справа.
    stack.replaceChildren();
    Object.assign(stack.style, { gap: '12px', width: '100%' });
    for (const [name, label, type, value] of fields) {
      const field = fieldSource.cloneNode(true);
      const input = field.querySelector('input');
      const caption = field.querySelector('label');
      input.setAttribute('name', name);
      input.setAttribute('id', `profile-${name}`);
      input.setAttribute('type', type);
      input.value = value;
      if (type === 'password') input.setAttribute('placeholder', 'Новый пароль');
      caption.textContent = label;
      caption.setAttribute('for', `profile-${name}`);
      stack.append(field);
    }
    const hint = document.createElement('p');
    hint.className = 'muted';
    hint.textContent =
      'Логин и пароль — для входа. Имя, город, возраст и род деятельности агенты используют в ответах.';
    stack.append(hint);
    const save = form.querySelector('button[type="submit"]');
    save.textContent = 'Сохранить';
    stack.append(save);
    form.remove();

    // --- 2. Своя картинка фона — в блок «Фон» секции «Внешний вид» ---
    const backgroundRow = background.querySelector('.row');
    const backgroundNote = document.createElement('p');
    backgroundNote.className = 'muted';
    backgroundNote.textContent =
      'Своя картинка затемняется автоматически; пресеты — выше.';
    const backgroundHeading = [...appearance.querySelectorAll('h2')].find(
      (node) => node.textContent.trim() === 'Фон',
    );
    if (backgroundHeading) {
      backgroundHeading.parentElement.append(backgroundNote, backgroundRow);
      background.remove();
    }

    // --- 3. Нижняя навигация дублирует меню аватара в топбаре ---
    nav?.remove();

    // --- 4. Подзаголовок страницы ---
    const subtitle = [...document.querySelectorAll('p')].find((p) =>
      p.textContent.includes('Аккаунт, контекст для агента'),
    );
    if (subtitle) subtitle.textContent = 'Аккаунт, личные данные и внешний вид.';

    return { ok: true };
  },
  { fields: FIELDS },
);
console.log('mutation', JSON.stringify(report));

// Мобильная раскладка: поля под аватаром.
await page.addStyleTag({
  content:
    '@media (max-width: 760px){ section.panel > .row{ grid-template-columns: 1fr !important; } }',
});

await page.waitForTimeout(400);
await page.screenshot({ path: `${OUT}/profile-v2-wide.png`, fullPage: true });

await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(400);
await page.screenshot({ path: `${OUT}/profile-v2-mobile.png`, fullPage: true });

await context.close();
await browser.close();
