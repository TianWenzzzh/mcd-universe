import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const p = await ctx.newPage();
await p.goto('http://127.0.0.1:8811/demo/', { waitUntil: 'load' });
await p.waitForSelector('#onboard.show', { timeout: 15000 });
await p.waitForTimeout(900);
const box = await p.locator('#onboard .ob-card').boundingBox();
console.log('ob-card', JSON.stringify(box));
await p.screenshot({ path: '.audit/onboard-2x.png', clip: { x: box.x-16, y: box.y-16, width: box.width+32, height: box.height+32 } });
const info = await p.evaluate(() => {
  const out = {};
  out.dpr = devicePixelRatio;
  const card = document.querySelector('#onboard .ob-card');
  const cs = getComputedStyle(card);
  out.card = { filter: cs.filter, backdrop: cs.backdropFilter, bg: cs.backgroundColor, transform: cs.transform, tfOrigin: cs.transformOrigin };
  const wrap = document.querySelector('#onboard');
  const ws = getComputedStyle(wrap);
  out.wrap = { filter: ws.filter, backdrop: ws.backdropFilter, bg: ws.backgroundColor };
  // any ancestor transform
  let n = card.parentElement, chain = [];
  while (n && n !== document.documentElement) { const c = getComputedStyle(n); chain.push([n.id||n.className, c.transform, c.filter, c.zoom]); n = n.parentElement; }
  out.chain = chain;
  return out;
});
console.log(JSON.stringify(info, null, 1));
await b.close();
