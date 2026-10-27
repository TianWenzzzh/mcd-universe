import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const p = await ctx.newPage();
await p.goto('http://127.0.0.1:8811/demo/', { waitUntil: 'load' });
await p.waitForSelector('#onboard.show', { timeout: 15000 });
await p.waitForTimeout(800);
const box = await p.locator('#onboard .onboard-card').boundingBox().catch(()=>null);
console.log('card box', JSON.stringify(box));
if (box) await p.screenshot({ path: '.audit/onboard-2x.png', clip: { x: box.x-20, y: box.y-20, width: box.width+40, height: box.height+40 } });
const st = await p.evaluate(() => {
  const el = document.querySelector('#onboard .onboard-card') || document.querySelector('#onboard');
  const cs = getComputedStyle(el);
  return { filter: cs.filter, backdrop: cs.backdropFilter, opacity: cs.opacity, tf: cs.transform, willChange: cs.willChange, zoom: cs.zoom };
});
console.log('card style', JSON.stringify(st));
await b.close();
