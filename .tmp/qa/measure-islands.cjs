const { chromium } = require('playwright');

const BASE = 'http://127.0.0.1:4173';

async function mock(page) {
  await page.route('**/sw.js', (r) => r.fulfill({ body: '', contentType: 'application/javascript' }));
  await page.route(
    (u) => u.pathname.startsWith('/api/'),
    async (route) => {
      const p = new URL(route.request().url()).pathname;
      if (p === '/api/me') return route.fulfill({ json: { id: 1, username: 'demo', is_owner: true } });
      if (p === '/api/profile') return route.fulfill({ json: { data: { onboarding_done: true }, summary: null } });
      if (p === '/api/notifications') return route.fulfill({ json: { items: [], unread_count: 2 } });
      if (p === '/api/spheres') return route.fulfill({ json: [{ id: 1, name: 'Здоровье', color: '#22c55e' }] });
      if (p.startsWith('/api/events')) return route.fulfill({ json: [] });
      return route.fulfill({ json: {} });
    },
  );
}

(async () => {
  const browser = await chromium.launch();
  const widths = [390, 899, 900, 940, 959, 960, 1000, 1024, 1025, 1026, 1280, 1440];
  for (const width of widths) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    await mock(page);
    await page.goto(BASE + '/calendar');
    await page.waitForSelector('aside[aria-label="Навигация"]');
    await page.waitForTimeout(400);
    const m = await page.evaluate(() => {
      const r = (el) => {
        if (!el) return null;
        const b = el.getBoundingClientRect();
        return { x: +b.x.toFixed(1), y: +b.y.toFixed(1), w: +b.width.toFixed(1), h: +b.height.toFixed(1), right: +(b.x + b.width).toFixed(1) };
      };
      const side = document.querySelector('aside[aria-label="Навигация"]');
      const search = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Поиск по Atlas'));
      const header = document.querySelector('header');
      const actions = header ? [...header.children].find((c) => c.tagName === 'DIV') : null;
      const profile = [...document.querySelectorAll('button')].find((b) => (b.getAttribute('aria-label') || '').startsWith('Профиль'));
      const s = r(search);
      let topAtSearchLeft = null;
      if (s) {
        const el = document.elementFromPoint(s.x + 8, s.y + s.h / 2);
        topAtSearchLeft = el ? `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 40)}|${(el.textContent || '').trim().slice(0, 30)}` : null;
      }
      return {
        sidebar: r(side),
        search: s,
        actions: r(actions),
        profile: r(profile),
        topAtSearchLeft,
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        bodyScrollWidth: document.body.scrollWidth,
        calendarSeg: (() => {
          const seg = document.querySelector('.fc') || document.querySelector('[role="tablist"]');
          if (!seg) return null;
          const b = seg.getBoundingClientRect();
          return { x: +b.x.toFixed(1), right: +(b.x + b.width).toFixed(1), w: +b.width.toFixed(1) };
        })(),
      };
    });
    console.log(JSON.stringify({ width, ...m }));
    if ([900, 940].includes(width)) {
      await page.screenshot({ path: `.tmp/qa/overlap-${width}.png` });
    }
    await context.close();
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
