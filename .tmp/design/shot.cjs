const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('@playwright/test');

const root = path.resolve(__dirname);
const file = 'file:///' + path.join(root, 'mockup.html').replace(/\\/g, '/');
const out = path.join(root, 'out');
fs.mkdirSync(out, { recursive: true });
for (const name of fs.readdirSync(out)) {
  fs.rmSync(path.join(out, name));
}

const shots = [
  { name: 'graphite-home-dark', screen: 'home', mode: 'dark', accent: '#1d4ed8', height: 1000 },
  { name: 'graphite-home-dark-emerald', screen: 'home', mode: 'dark', accent: '#059669', height: 1000 },
  { name: 'graphite-chat-dark', screen: 'chat', mode: 'dark', accent: '#1d4ed8', height: 900 },
  { name: 'graphite-settings-dark', screen: 'settings', mode: 'dark', accent: '#1d4ed8', height: 940 },
  { name: 'graphite-home-light', screen: 'home', mode: 'light', accent: '#1d4ed8', height: 1000 },
  { name: 'graphite-settings-light', screen: 'settings', mode: 'light', accent: '#1d4ed8', height: 940 },
];

(async () => {
  const browser = await chromium.launch();
  for (const shot of shots) {
    const page = await browser.newPage({
      viewport: { width: 1440, height: shot.height },
      deviceScaleFactor: 1.5,
    });
    const query = `screen=${shot.screen}&mode=${shot.mode}&accent=${encodeURIComponent(shot.accent)}`;
    await page.goto(`${file}?${query}`);
    await page.waitForTimeout(300);
    const target = path.join(out, `${shot.name}.png`);
    await page.screenshot({ path: target });
    await page.close();
    console.log('ok', target);
  }
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
