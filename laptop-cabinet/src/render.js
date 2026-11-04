// Renders the 3D views used on the drawing sheets.  node render.js <render.html> <outdir>
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const [page_html, outdir] = process.argv.slice(2);
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 }, deviceScaleFactor: 2 });
  page.on('console', m => console.log('page:', m.text()));
  page.on('pageerror', e => console.log('pageerror:', e.message));
  await page.goto('file://' + path.resolve(page_html));
  await page.waitForFunction(() => window.ready === true);
  const shots = [
    ['iso_empty', { mode: 'empty', view: 'iso' }],
    ['iso_loaded', { mode: 'loaded', view: 'iso' }],
    ['exploded', { mode: 'exploded', view: 'iso', callouts: true, zoom: 0.92, lift: 9 }],
    ['rear_iso', { mode: 'empty', view: 'rear' }],
    ['iso_doors', { mode: 'empty', view: 'iso', doors: true }],
    ['front_loaded', { mode: 'loaded', view: 'front' }],
  ];
  for (const [name, o] of shots) {
    await page.evaluate(o => window.show(o), o);
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(outdir, name + '.png') });
    console.log('wrote', name);
  }
  await browser.close();
})();
