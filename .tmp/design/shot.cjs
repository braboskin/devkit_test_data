const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('@playwright/test');

const root = path.resolve(__dirname);
const file = 'file:///' + path.join(root, 'mockup.html').replace(/\\/g, '/');
const out = path.join(root, 'out');
fs.mkdirSync(out, { recursive: true });

const palettes = ['navy', 'graphite', 'violet'];
const screens = [
  { name: 'home', height: 1000 },
  { name: 'chat', height: 900 },
];

(async () => {
  const browser = await chromium.launch();
  for (const palette of palettes) {
    for (const screen of screens) {
      const page = await browser.newPage({
        viewport: { width: 1440, height: screen.height },
        deviceScaleFactor: 1.5,
      });
      await page.goto(`${file}?palette=${palette}&screen=${screen.name}`);
      await page.waitForTimeout(300);
      const target = path.join(out, `${palette}-${screen.name}.png`);
      await page.screenshot({ path: target });
      await page.close();
      console.log('ok', target);
    }
  }
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
