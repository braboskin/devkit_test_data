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

async function measure(page) {
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
      overlap: s && side ? +(side.getBoundingClientRect().right - s.x).toFixed(1) : null,
      innerWidth: window.innerWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
      innerHeight: window.innerHeight,
      mediaDesktop: matchMedia('(min-width: 900px)').matches,
    };
  });
}

(async () => {
  const browser = await chromium.launch({ args: ['--disable-features=OverlayScrollbar'] });
  for (const width of [900, 905, 910, 940, 959, 960]) {
    const context = await browser.newContext({ viewport: { width, height: 700 } });
    const page = await context.newPage();
    await mock(page);
    await page.goto(BASE + '/spheres');
    await page.waitForSelector('aside[aria-label="Навигация"]');
    await page.waitForTimeout(500);
    console.log('classic-scrollbar', JSON.stringify({ width, ...(await measure(page)) }));
    await context.close();
  }
  await browser.close();

  // explicit dark theme axe at 1440 and 390
  const browser2 = await chromium.launch();
  for (const [theme, width] of [['dark', 1440], ['dark', 390], ['light', 390]]) {
    const context = await browser2.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    await mock(page);
    await page.goto(BASE + '/calendar');
    await page.waitForSelector('aside[aria-label="Навигация"]');
    await page.evaluate((t) => { document.documentElement.dataset.theme = t; }, theme);
    await page.waitForTimeout(300);
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
    console.log('axe', JSON.stringify({ theme, width, themeAttr: await page.evaluate(() => document.documentElement.dataset.theme), serious: serious.length, all: results.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, targets: v.nodes.slice(0, 3).map((n) => n.target.join(' ')) })) }));
    await context.close();
  }

  // dark theme reduced-transparency
  const context = await browser2.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-transparency', value: 'reduce' }] });
  await mock(page);
  await page.goto(BASE + '/');
  await page.waitForSelector('aside[aria-label="Навигация"]');
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
  await page.waitForTimeout(300);
  const styles = await page.evaluate(() => {
    const pick = (el) => {
      const s = getComputedStyle(el);
      return { bg: s.backgroundColor, blur: s.backdropFilter || s.webkitBackdropFilter, shadow: s.boxShadow.slice(0, 80) };
    };
    const side = document.querySelector('aside[aria-label="Навигация"]');
    const search = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Поиск по Atlas'));
    return { matches: matchMedia('(prefers-reduced-transparency: reduce)').matches, theme: document.documentElement.dataset.theme, sidebar: pick(side), search: pick(search) };
  });
  console.log('reduced-transparency-dark', JSON.stringify(styles));
  await context.close();
  await browser2.close();
})().catch((e) => { console.error(e); process.exit(1); });
