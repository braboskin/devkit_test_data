import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json',
);
const { chromium } = require('@playwright/test');

const MOCKS = {
  '/api/me': { id: 'u1', username: 'Михаил' },
  '/api/profile': { data: { onboarding_done: true }, summary: null, updated_at: null },
  '/api/notifications': { items: [], unread_count: 0 },
  '/api/spheres': [{ id: 1, name: 'Здоровье', color: '#34d399' }],
  '/api/projects': [],
  '/api/events': [],
};

async function main() {
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
  await page.goto('http://localhost:5174/calendar', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const info = await page.evaluate(() => {
    const node = document.querySelector('.fc-daygrid-week-number');
    const dayNumber = document.querySelector('.fc-daygrid-day-number');
    if (!node) {
      return 'no week number node';
    }
    const style = getComputedStyle(node);
    const box = node.getBoundingClientRect();
    const dayBox = dayNumber?.getBoundingClientRect();
    return {
      position: style.position,
      float: style.float,
      display: style.display,
      width: style.width,
      padding: style.padding,
      margin: style.margin,
      box: [box.x, box.y, box.width, box.height],
      day: dayBox ? [dayBox.x, dayBox.y, dayBox.width, dayBox.height] : null,
      html: node.outerHTML.slice(0, 200),
    };
  });
  console.log(JSON.stringify(info, null, 2));
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
