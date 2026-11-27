import { createRequire } from 'node:module';
const require = createRequire('X:/devkit_projects/projects/atlas/repo/atlas/viewer/package.json');
const { chromium } = require('@playwright/test');
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await context.addInitScript(() => {
  window.localStorage.setItem('atlas.theme', JSON.stringify({ mode: 'dark', accent: '#334155', effects: true, background: 'none' }));
});
const page = await context.newPage();
await page.route('**/*', async (route) => {
  const p = new URL(route.request().url()).pathname;
  if (!p.startsWith('/api/')) return route.fallback();
  const body = p === '/api/me' ? { id: 'u1', username: 'Михаил' } : p === '/api/profile' ? { data: { onboarding_done: true }, summary: null, updated_at: null } : p === '/api/notifications' ? { items: [], unread_count: 0 } : [];
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
});
await page.goto('http://localhost:5173/nope', { waitUntil: 'networkidle' });
await page.waitForTimeout(400);
const info = await page.evaluate(() => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (node.textContent && node.textContent.includes('Поиск по Atlas')) {
      let el = node.parentElement;
      const chain = [];
      for (let i = 0; i < 4 && el; i += 1) {
        const s = getComputedStyle(el);
        chain.push({ tag: el.tagName.toLowerCase(), cls: el.className, bg: s.backgroundColor, color: s.color });
        el = el.parentElement;
      }
      return chain;
    }
  }
  return null;
});
console.log(JSON.stringify(info, null, 2));
const svgs = await page.evaluate(() => document.querySelectorAll('.ant-result-icon svg, .ant-result-icon img').length);
console.log('result icon nodes:', svgs);
await browser.close();
