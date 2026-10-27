import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");
const b = await chromium.launch();
async function run(name, vp, mobile) {
  const ctx = await b.newContext({ viewport: vp, isMobile: !!mobile, hasTouch: !!mobile, deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  await p.goto('http://127.0.0.1:8811/demo/', { waitUntil: 'load' });
  await p.waitForSelector('#onboard.show', { timeout: 15000 });
  await p.click('#ob-go');
  await p.waitForTimeout(2500);
  await p.click('#btn-dex');
  await p.waitForTimeout(700);
  await p.screenshot({ path: `.audit/${name}-dex.png` });
  const geo = await p.evaluate(() => {
    const r = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) }; };
    const dex = document.querySelector('#dex-panel');
    const cs = getComputedStyle(dex);
    return { dex: r('#dex-panel'), btns: r('#btn-dex'), detail: r('#detail'), footer: r('#footer'), scrollH: dex.scrollHeight, clientH: dex.clientHeight, z: cs.zIndex, items: document.querySelectorAll('.dex-item').length, aria: dex.getAttribute('aria-expanded') };
  });
  console.log(name, JSON.stringify(geo));
  await ctx.close();
}
await run('d', { width: 1440, height: 900 });
await run('m', { width: 390, height: 844 }, true);
await b.close();
