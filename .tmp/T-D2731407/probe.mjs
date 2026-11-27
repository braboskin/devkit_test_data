import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'mihail', display_name: 'Михаил', is_owner: true },
  '/api/profile': {
    data: { onboarding_done: true, ui: { background_ref: 'demo' } },
    summary: 'Сферы: Здоровье, Работа; Проекты: Atlas',
    updated_at: null,
  },
  '/api/notifications': { items: [], unread_count: 0 },
};

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
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
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(MOCKS[url.pathname] ?? []),
  });
});
await page.goto('http://localhost:5174/profile');
await page.getByText('Контекст для агента').first().waitFor({ timeout: 15000 });
await page.waitForTimeout(500);
const info = await page.evaluate(() => {
  const form = [...document.querySelectorAll('form')].find((node) =>
    node.textContent.includes('Контекст для агента'),
  );
  const inputs = [...(form?.querySelectorAll('input') ?? [])];
  const first = inputs[0];
  const cs = first ? getComputedStyle(first) : null;
  return {
    formTag: form?.tagName ?? null,
    formClass: form?.className ?? null,
    formHtml: form?.outerHTML.slice(0, 2600) ?? null,
    inputStyle: cs
      ? {
          background: cs.backgroundColor,
          border: cs.border,
          borderRadius: cs.borderRadius,
          padding: cs.padding,
          color: cs.color,
          font: cs.font,
          boxShadow: cs.boxShadow,
          height: cs.height,
        }
      : null,
  };
});
console.log(JSON.stringify(info, null, 2));
await context.close();
await browser.close();
