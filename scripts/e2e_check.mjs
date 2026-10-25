/**
 * E2E 冒烟检查：用真实浏览器打开演示页，验证
 * 1. 页面无控制台错误 / 未捕获异常
 * 2. 星点已渲染
 * 3. 分享卡 composeCard() 产出合法 1080x1440 PNG（落盘供人工查看）
 * 4. 三态（银河 / 星云 / 甜点）均可打开
 *
 * 用法（需要 playwright-core）：
 *   node scripts/e2e_check.mjs [baseUrl]
 * 依赖安装：npm i -D playwright-core（或使用全局已装的 Edge channel）
 */
import { writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const BASE = process.argv[2] || "https://tianwenzzzh.github.io/mcd-universe/demo/";
const OUT_DIR = process.argv[3] || "docs/assets";

async function checkPage(browser, url, opts) {
  const page = await browser.newPage({ viewport: opts.viewport });
  const problems = [];
  page.on("console", (m) => {
    if (m.type() === "error") problems.push("console: " + m.text());
  });
  page.on("pageerror", (e) => problems.push("pageerror: " + String(e)));
  await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(4500);
  const state = await page.evaluate(() => {
    const mc = window.__mcuniverse;
    return {
      stars: mc ? mc.stars.length : -1,
      isNebula: mc ? mc.isNebula : null,
      reduced: mc ? mc.reduced : null,
      persona: mc && mc.data.persona ? mc.data.persona.name : null,
    };
  });
  if (opts.expectNebula !== undefined && state.isNebula !== opts.expectNebula) {
    problems.push(`默认星云态不符: ${state.isNebula}`);
  }
  if (opts.expectStars && state.stars !== opts.expectStars) {
    problems.push(`星点数不符: ${state.stars} != ${opts.expectStars}`);
  }
  if (opts.exportCard) {
    const card = await page.evaluate(() => {
      const ec = window.__mcuniverse.composeCard();
      return { w: ec.width, h: ec.height, data: ec.toDataURL("image/png") };
    });
    if (card.w !== 1080 || card.h !== 1440) problems.push(`分享卡尺寸错误: ${card.w}x${card.h}`);
    const b64 = card.data.split(",")[1] || "";
    if (b64.length < 50000) problems.push(`分享卡内容是空的（base64 ${b64.length} 字符）`);
    writeFileSync(`${OUT_DIR}/share-card-e2e.png`, Buffer.from(b64, "base64"));
    state.cardBytes = b64.length;
  }
  await page.close();
  return { url, state, problems };
}

async function main() {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const results = [];
  results.push(
    await checkPage(browser, BASE + "?e2e=1", {
      viewport: { width: 1280, height: 720 },
      expectNebula: false,
      expectStars: 10,
      exportCard: true,
    }),
  );
  results.push(
    await checkPage(browser, BASE + "?nebula=1&e2e=1", {
      viewport: { width: 390, height: 844 },
      expectNebula: true,
      expectStars: 0,
    }),
  );
  results.push(
    await checkPage(browser, BASE + "dessert.html?e2e=1", {
      viewport: { width: 1280, height: 720 },
      expectNebula: false,
      expectStars: 10,
    }),
  );
  await browser.close();

  let failed = 0;
  for (const r of results) {
    const ok = r.problems.length === 0;
    if (!ok) failed++;
    console.log(`${ok ? "PASS" : "FAIL"} ${r.url}`);
    console.log(`     stars=${r.state.stars} nebula=${r.state.isNebula} persona=${r.state.persona}` +
      (r.state.cardBytes ? ` card=${Math.round(r.state.cardBytes / 1024)}KB` : ""));
    r.problems.forEach((p) => console.log("     - " + p));
  }
  process.exit(failed ? 1 : 0);
}

main().catch((e) => {
  console.error("E2E 运行失败:", e);
  process.exit(1);
});
