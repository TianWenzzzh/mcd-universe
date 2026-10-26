/**
 * 投稿截图生成器：一张命令重拍全部投稿图，避免"改了界面、截图还是旧的"。
 *
 * 产出（docs/assets/）：
 *   submit-1.png  桌面主界面（悬停气泡 + 人格卡与成就，投稿第一张）
 *   submit-2.png  分享卡四种风格导出面板
 *   submit-3.png  移动端竖屏
 *   demo-detail.png  单颗星的详情面板（README / 说明页用）
 *
 * 用法（需要 playwright-core）：
 *   node scripts/make_shots.mjs [baseUrl] [outDir]
 * 默认 1280x800 @1.5x（成图 1920x1200）与 390x844 @2x（成图 780x1688）。
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const BASE = process.argv[2] || "http://127.0.0.1:8123/demo/";
const OUT = process.argv[3] || "docs/assets";

/** 关掉首访引导，并把入场动画放完 */
async function settle(page, ms = 6200) {
  await page.evaluate(() => {
    if (window.__mcuniverse && window.__mcuniverse.dismissOnboard) {
      window.__mcuniverse.dismissOnboard();
    }
  });
  await page.waitForTimeout(ms);
}

async function main() {
  const browser = await chromium.launch({ channel: "msedge", headless: true });

  // 1. 桌面主界面：挑一颗偏外侧的星悬停，让气泡出现在星群空隙里而不是压住星点
  const desk = await browser.newPage({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1.5,
  });
  await desk.goto(BASE + "?shot=1", { waitUntil: "domcontentloaded" });
  await settle(desk);
  const target = await desk.evaluate(() => {
    const stars = window.__mcuniverse.stars;
    // 优先挑"排得开"的一颗：离其他星最远的那个，气泡不会盖住邻居
    let best = null, bestD = -1;
    for (const s of stars) {
      let d = Infinity;
      for (const o of stars) if (o !== s) d = Math.min(d, Math.hypot(o.x - s.x, o.y - s.y));
      if (d > bestD) { bestD = d; best = s; }
    }
    return best ? { x: Math.round(best.x), y: Math.round(best.y) } : null;
  });
  if (target) {
    await desk.mouse.move(target.x, target.y);
    await desk.waitForTimeout(500);
  }
  await desk.screenshot({ path: `${OUT}/submit-1.png` });
  console.log("shot submit-1.png");

  // 2. 导出面板
  await desk.click("#btn-save");
  await desk.waitForTimeout(900);
  await desk.screenshot({ path: `${OUT}/submit-2.png` });
  console.log("shot submit-2.png");

  // 2b. 详情面板：关掉面板后点一颗星（1 倍图，README 用）
  await desk.keyboard.press("Escape");
  await desk.waitForTimeout(400);
  const detail = await browser.newPage({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
  });
  await detail.goto(BASE + "?shot=2", { waitUntil: "domcontentloaded" });
  await settle(detail);
  const pick = await detail.evaluate(() => {
    // 选最靠右的一颗：详情卡在右侧展开时不会压住左边的人格卡
    let best = null;
    for (const s of window.__mcuniverse.stars) if (!best || s.x > best.x) best = s;
    return best ? { x: Math.round(best.x), y: Math.round(best.y) } : null;
  });
  if (pick) {
    await detail.mouse.click(pick.x, pick.y);
    await detail.waitForTimeout(600);
  }
  await detail.screenshot({ path: `${OUT}/demo-detail.png` });
  console.log("shot demo-detail.png");
  await detail.close();
  await desk.close();

  // 3. 移动端
  const mob = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  await mob.goto(BASE + "?shot=3", { waitUntil: "domcontentloaded" });
  await settle(mob);
  await mob.screenshot({ path: `${OUT}/submit-3.png` });
  console.log("shot submit-3.png");
  await mob.close();

  await browser.close();
}

main().catch((e) => {
  console.error("截图失败:", e);
  process.exit(1);
});
