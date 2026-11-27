import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(() => {
    window.localStorage.setItem(
      'atlas.theme',
      JSON.stringify({ mode: 'dark', accent: '#334155', effects: true, background: 'none' }),
    );
  });
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (!pathname.startsWith('/api/')) {
      await route.fallback();
      return;
    }
    const body =
      pathname === '/api/me'
        ? { id: 'u1', username: 'Михаил' }
        : pathname === '/api/profile'
          ? { data: { onboarding_done: true }, summary: null, updated_at: null }
          : pathname === '/api/notifications'
            ? { items: [], unread_count: 0 }
            : [];
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('http://localhost:5173/nope', { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const info = await page.evaluate(() => {
    const search = document.querySelector('header button');
    const searchStyle = search ? getComputedStyle(search) : null;
    const resultImage = document.querySelector('.ant-result-image');
    const custom = document.querySelector('.ant-result-icon svg');
    return {
      theme: document.documentElement.dataset['theme'],
      effects: document.documentElement.dataset['effects'],
      sunken: getComputedStyle(document.documentElement).getPropertyValue('--sunken'),
      search: search
        ? { cls: search.className, bg: searchStyle.backgroundColor, color: searchStyle.color, border: searchStyle.borderColor }
        : null,
      hasAntdImage: Boolean(resultImage),
      customSvgParent: custom?.parentElement?.className ?? null,
    };
  });
  console.log(JSON.stringify(info, null, 2));
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
