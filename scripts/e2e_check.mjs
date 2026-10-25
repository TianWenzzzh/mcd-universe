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
  if (opts.reducedMotion) await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
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
    const cards = await page.evaluate(() => {
      return ["deep", "nebula", "minimal"].map((style) => {
        const ec = window.__mcuniverse.composeCard(style);
        return { style, w: ec.width, h: ec.height, data: ec.toDataURL("image/png") };
      });
    });
    state.cards = {};
    for (const card of cards) {
      if (card.w !== 1080 || card.h !== 1440) problems.push(`${card.style} 尺寸错误: ${card.w}x${card.h}`);
      const b64 = card.data.split(",")[1] || "";
      if (b64.length < 50000) problems.push(`${card.style} 内容是空的（base64 ${b64.length} 字符）`);
      state.cards[card.style] = b64.length;
      if (card.style === "deep") writeFileSync(`${OUT_DIR}/share-card-e2e.png`, Buffer.from(b64, "base64"));
      if (card.style === "minimal") writeFileSync(`${OUT_DIR}/share-card-minimal.png`, Buffer.from(b64, "base64"));
      if (card.style === "nebula") writeFileSync(`${OUT_DIR}/share-card-nebula.png`, Buffer.from(b64, "base64"));
    }
    state.cardBytes = Object.values(state.cards).join("/");
  }
  if (opts.ui) {
    // 首访引导会拦截点击：先关掉（同时验证引导层可关闭）
    await page.evaluate(() => {
      try { localStorage.setItem("mcuniverse_onboarded", "1"); } catch (e) {}
      document.getElementById("onboard").classList.remove("show");
    });
    await page.waitForTimeout(200);
    // 真实点击：保存分享卡 → 面板展开 → 点「极简海报」→ 触发下载
    await page.click("#btn-save");
    await page.waitForTimeout(600);
    const panelOpen = await page.evaluate(() => document.getElementById("export-panel").classList.contains("show"));
    if (!panelOpen) problems.push("导出面板未展开（按钮可能被遮挡）");
    const previewCount = await page.evaluate(() => {
      const cvs = [...document.querySelectorAll(".ep-style canvas")];
      return cvs.filter((c) => {
        const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
        for (let i = 3; i < d.length; i += 4) if (d[i] > 0) return true;
        return false;
      }).length;
    });
    if (previewCount !== 3) problems.push(`风格预览应为 3 张，实际绘出 ${previewCount}`);
    const downloadPromise = page.waitForEvent("download", { timeout: 15000 }).catch(() => null);
    await page.click('.ep-style[data-style="minimal"]');
    const dl = await downloadPromise;
    if (!dl) problems.push("点击风格后未触发下载");
    else state.download = dl.suggestedFilename();

    // 键盘：方向键逐颗浏览，详情面板应展开
    await page.keyboard.press("Escape");
    await page.focus("#sky");
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(300);
    const detailShown = await page.evaluate(() => document.getElementById("detail").classList.contains("show"));
    if (!detailShown) problems.push("键盘方向键未能选中星点");
    const liveText = await page.evaluate(() => document.getElementById("a11y-live").textContent);
    if (!liveText || !liveText.includes("颗星")) problems.push("aria-live 未播报选中信息");

    // 悬停：鼠标移到第一颗星，应出现餐品气泡
    const pos = await page.evaluate(() => {
      const s = window.__mcuniverse.stars[0];
      return s ? { x: Math.round(s.x), y: Math.round(s.y) } : null;
    });
    if (pos) {
      await page.mouse.move(pos.x, pos.y);
      await page.waitForTimeout(300);
      const tipShown = await page.evaluate(() => getComputedStyle(document.getElementById("tip")).display !== "none");
      if (!tipShown) problems.push("悬停未出现餐品气泡");
    }
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
      ui: true,
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
  const rm = await checkPage(browser, BASE + "?e2e=1&rm=1", {
    viewport: { width: 1280, height: 720 },
    expectNebula: false,
    expectStars: 10,
    reducedMotion: true,
  });
  if (rm.state.reduced !== true) rm.problems.push("prefers-reduced-motion 未生效");
  results.push(rm);
  await browser.close();

  let failed = 0;
  for (const r of results) {
    const ok = r.problems.length === 0;
    if (!ok) failed++;
    console.log(`${ok ? "PASS" : "FAIL"} ${r.url}`);
    console.log(`     stars=${r.state.stars} nebula=${r.state.isNebula} persona=${r.state.persona}` +
      (r.state.cards ? ` cards=${Object.entries(r.state.cards).map(([k, v]) => k + ":" + Math.round(v / 1024) + "KB").join(" ")}` : ""));
    if (r.state.download) console.log(`     download=${r.state.download}`);
    r.problems.forEach((p) => console.log("     - " + p));
  }
  process.exit(failed ? 1 : 0);
}

main().catch((e) => {
  console.error("E2E 运行失败:", e);
  process.exit(1);
});
