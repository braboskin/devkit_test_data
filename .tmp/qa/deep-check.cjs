const { chromium } = require('playwright');
const AxeBuilder = require('@axe-core/playwright').default;

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

async function boxes(page) {
  return page.evaluate(() => {
    const r = (el) => {
      if (!el) return null;
      const b = el.getBoundingClientRect();
      return { x: +b.x.toFixed(1), w: +b.width.toFixed(1), right: +(b.x + b.width).toFixed(1) };
    };
    const side = document.querySelector('aside[aria-label="Навигация"]');
    const search = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Поиск по Atlas'));
    const s = r(search);
    return {
      sidebar: r(side),
      search: s,
      centerDelta: s ? +(s.x + s.w / 2 - window.innerWidth / 2).toFixed(1) : null,
      innerWidth: window.innerWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
      innerHeight: window.innerHeight,
    };
  });
}

(async () => {
  const browser = await chromium.launch();

  for (const [width, path] of [[900, '/spheres'], [900, '/calendar'], [1280, '/'], [1440, '/']]) {
    const context = await browser.newContext({ viewport: { width, height: 800 } });
    const page = await context.newPage();
    await mock(page);
    await page.goto(BASE + path);
    await page.waitForSelector('aside[aria-label="Навигация"]');
    await page.waitForTimeout(500);
    console.log('layout', JSON.stringify({ width, path, ...(await boxes(page)) }));
    await context.close();
  }

  // axe on light and dark at 1440
  for (const theme of ['dark', 'light']) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await mock(page);
    await page.goto(BASE + '/calendar');
    await page.waitForSelector('aside[aria-label="Навигация"]');
    if (theme === 'light') {
      await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
    }
    await page.waitForTimeout(300);
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
    console.log('axe', JSON.stringify({ theme, violations: results.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, targets: v.nodes.slice(0, 3).map((n) => n.target.join(' ')) })), serious: serious.length }));
    await context.close();
  }

  // reduced transparency emulation
  for (const theme of ['dark', 'light']) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send('Emulation.setEmulatedMedia', {
      features: [{ name: 'prefers-reduced-transparency', value: 'reduce' }],
    });
    await mock(page);
    await page.goto(BASE + '/');
    await page.waitForSelector('aside[aria-label="Навигация"]');
    if (theme === 'light') {
      await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
    }
    await page.waitForTimeout(300);
    const styles = await page.evaluate(() => {
      const side = document.querySelector('aside[aria-label="Навигация"]');
      const search = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Поиск по Atlas'));
      const cs = (el) => {
        const s = getComputedStyle(el);
        return { bg: s.backgroundColor, blur: s.backdropFilter || s.webkitBackdropFilter, highlight: s.boxShadow.slice(0, 60) };
      };
      return {
        matches: matchMedia('(prefers-reduced-transparency: reduce)').matches,
        sidebar: cs(side),
        search: cs(search),
      };
    });
    console.log('reduced-transparency', JSON.stringify({ theme, ...styles }));
    await context.close();
  }

  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
