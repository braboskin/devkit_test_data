import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const OUT = 'X:/devkit_projects/projects/atlas/.tmp/T-D2731407/out';
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

async function installMocks(page) {
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
}

async function main() {
  mkdirSync(OUT, { recursive: true });
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
  await installMocks(page);

  // --- Настройки: до/после ---
  await page.goto('http://localhost:5174/settings');
  await page.getByText('Сводка профиля').first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/settings-before.png`, fullPage: true });
  await page.addStyleTag({
    content: '[aria-labelledby="profile-heading"]{display:none!important}',
  });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/settings-after.png`, fullPage: true });

  // --- Профиль: до/после ---
  await page.goto('http://localhost:5174/profile');
  await page.getByText('Контекст для агента').first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/profile-before.png`, fullPage: true });

  const report = await page.evaluate(() => {
    const form = [...document.querySelectorAll('form')].find((node) =>
      node.textContent.includes('Контекст для агента'),
    );
    if (!form) return { ok: false, reason: 'form not found' };
    const row = form.querySelector('.row');
    const field = row?.children[0];
    const sourceInput = field?.querySelector('input');
    if (!row || !field || !sourceInput) {
      return { ok: false, reason: 'row/field/input not found' };
    }

    const textarea = document.createElement('textarea');
    textarea.className = sourceInput.className;
    textarea.id = 'summary';
    textarea.rows = 5;
    textarea.value =
      'Сферы: Здоровье, Работа. Проекты: Atlas. Цели: запустить v1. Важно: ясность, короткие ответы, никаких диагнозов.';
    Object.assign(textarea.style, {
      minHeight: '150px',
      resize: 'vertical',
      lineHeight: '1.5',
      padding: '10px 11px',
    });
    sourceInput.replaceWith(textarea);

    const label = field.querySelector('label');
    if (label) {
      label.textContent = 'О владельце (сводка профиля)';
      label.setAttribute('for', 'summary');
    }

    for (const node of [...row.children].slice(1)) node.remove();
    row.replaceWith(field);
    field.style.width = '100%';

    for (const node of [...form.children]) {
      if (node.querySelector('input[type="checkbox"]')) node.remove();
    }

    const heading = form.querySelector('h2');
    if (heading) heading.textContent = 'О владельце';
    const note = form.querySelector('p.muted');
    if (note) {
      note.textContent =
        'Сводка профиля попадает в промпт всем агентам: кто вы, чем занимаетесь и что важно учитывать.';
    }
    return { ok: true };
  });

  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/profile-after.png`, fullPage: true });
  console.log('mutation', JSON.stringify(report));

  await context.close();
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
