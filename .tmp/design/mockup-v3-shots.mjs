import { createRequire } from 'node:module';

const require = createRequire(
  'X:/devkit_projects/projects/atlas/repo/atlas/web/package.json',
);
const { chromium } = require('@playwright/test');

const URL = 'file:///X:/devkit_projects/projects/atlas/.tmp/design/mockup-v3.html';
const OUT = 'X:/devkit_projects/projects/atlas/.tmp/design/out';

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 1.5,
  });
  const page = await context.newPage();
  for (const name of ['shell', 'projects']) {
    await page.goto(`${URL}#${name}`);
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/mock-v3-${name}-dark.png` });
    console.log('ok', name);
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
