/**
 * 分享卡排版体检：把四张卡渲染出来跑一次像素统计，用数字找"缩略图里才显形"的排版病。
 *
 * 为什么需要它：卡片是 1080x1440，但真正被看到时只有一屏宽（~390pt，缩到 0.36 倍）。
 * 在这个尺度上，"中间空了 140px""脚注只剩 9px 下边距"这类问题在 1080 原图里几乎看不出来。
 * 上一轮就是靠它量出深空金版心被切成上下两截（1101~1245 全空）、脚注下边距 13px。
 *
 * 判定：
 *   空洞带  卡片内容首尾之间的连续空行（墨量 < 0.2%）。星图卡是"英雄区+信息带"结构，
 *           中间出现空洞必然是排版断了，阈值 120px；海报卡靠留白立版面，阈值 150px。
 *   二维码  二维码与左侧文字带（按 maxW 撑开）的间距 < 20px，换更长的文案就会贴上。
 *   底边    脚注字脚离卡片下沿 < 48px（微信/小红书会加圆角与边框，等于被切）。
 *
 * 几何断言（安全边距、行数、不重叠）在 e2e_check.mjs 里做，读的是 cardLayout() 规格本身，
 * 不依赖像素 —— 这里只负责像素层面的"观感"问题。
 *
 * 用法：node scripts/card_audit.mjs [baseUrl]
 */
import { createRequire } from "node:module";
import { writeFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const BASE = process.argv[2] || "http://127.0.0.1:8765/demo/";
const INK_LUM = 78;        // 高于此亮度算"墨"（深底 #05040e 亮度约 8~20）
const VOID_RATIO = 0.002;  // 该行墨量低于 0.2% 视为空行
const VOID_MAX = { deep: 120, nebula: 120, minimal: 150, achievement: 150 };
// 只在文字可能出现的区域里找空洞：星图卡 260~1090 是星场本身，亮像素少是正常的
const TEXT_REGIONS = {
  deep: [{ y0: 40, y1: 260 }, { y0: 1090, y1: 1420 }],
  nebula: [{ y0: 40, y1: 260 }, { y0: 1090, y1: 1420 }],
  minimal: [{ y0: 64, y1: 1376 }],
  achievement: [{ y0: 64, y1: 1376 }],
};
const MIN_QR_GAP = 20;
const MIN_BOTTOM = 48;
// 静区按 ISO/IEC 18004 要 4 个模块；模块边长低于 3px 时缩到一屏宽就糊成一团
const MIN_QR_QUIET = 4;
const MIN_QR_MODULE = 3;

function auditInPage({ style, INK_LUM, VOID_RATIO, VOID_MAX, regions }) {
  const mc = window.__mcuniverse;
  const L = mc.cardLayout(style);
  const ec = mc.composeCard(style);
  const { data } = ec.getContext("2d").getImageData(0, 0, 1080, 1440);
  const rows = new Array(1440).fill(0);
  let firstInk = -1;
  let lastInk = -1;
  for (let y = 0; y < 1440; y++) {
    let c = 0;
    const base = y * 1080 * 4;
    for (let x = 0; x < 1080; x++) {
      const i = base + x * 4;
      if (0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2] > INK_LUM) c++;
    }
    rows[y] = c / 1080;
    if (rows[y] >= VOID_RATIO && regions.some((r) => y >= r.y0 && y < r.y1)) {
      if (firstInk < 0) firstInk = y;
      lastInk = y;
    }
  }
  const inRegion = (y) => regions.some((r) => y >= r.y0 && y < r.y1);
  const voids = [];
  let start = -1;
  for (let y = firstInk; y <= lastInk; y++) {
    if (!inRegion(y)) { start = -1; continue; }
    const empty = rows[y] < VOID_RATIO;
    if (empty && start < 0) start = y;
    if ((!empty || y === lastInk) && start >= 0) {
      const h = y - start;
      if (h >= VOID_MAX) voids.push({ from: start, to: y, h });
      start = -1;
    }
  }
  const q = L.qr;
  // 只有"二维码靠右、文字在左"的星图卡存在这个间距问题；海报卡二维码居中，不适用
  const qrGap = L.desc && q.x > 540 ? Math.round(q.x - (540 + L.desc.maxW / 2)) : null;
  // 脚注字脚（descender 按 0.25em 估）到下沿的余量
  const bottomGap = Math.round(1440 - (L.footer + L.footerSize * 0.25));

  // 二维码能不能扫：白框的内缩就是静区，换算成模块数才和规范可比。
  // 沿框的中线取首个/末个黑像素 —— 圆角会让四个角本来就是底色，用角会量成 0。
  const lum = (x, y) => {
    const i = (y * 1080 + x) * 4;
    return 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
  };
  const qi = mc.qrInfo();
  const qs = Math.round(q.size);
  const qx = Math.round(q.x);
  const qy = Math.round(q.y);
  const mid = qs >> 1;
  let hx0 = -1, hx1 = -1, hy0 = -1, hy1 = -1;
  for (let i = 0; i < qs; i++) {
    if (lum(qx + i, qy + mid) < 128) { if (hx0 < 0) hx0 = i; hx1 = i; }
    if (lum(qx + mid, qy + i) < 128) { if (hy0 < 0) hy0 = i; hy1 = i; }
  }
  const code = hx1 - hx0 + 1;
  const modulePx = code / qi.modules;
  const quiet = Math.min(hx0, hy0, qs - 1 - hx1, qs - 1 - hy1) / modulePx;
  const pageIsPages = /(^|\.)github\.io$/.test(location.hostname);
  const hostOk = pageIsPages ? /github\.io/.test(qi.url) : !/github\.io/.test(qi.url);

  return {
    style, voids, qrGap, bottomGap,
    qr: { quiet, modulePx, code, inset: Math.min(hx0, hy0, qs - 1 - hx1, qs - 1 - hy1), url: qi.url, hostOk },
    png: ec.toDataURL("image/png").split(",")[1],
  };
}

const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.goto(BASE + "?e2e=1", { waitUntil: "domcontentloaded", timeout: 90000 });
await page.waitForTimeout(4000);

const out = [];
for (const style of ["deep", "nebula", "minimal", "achievement"]) {
  const r = await page.evaluate(auditInPage, {
    style, INK_LUM, VOID_RATIO, VOID_MAX: VOID_MAX[style], regions: TEXT_REGIONS[style],
  });
  writeFileSync(`docs/assets/share-card-${style === "deep" ? "e2e" : style}.png`, Buffer.from(r.png, "base64"));
  delete r.png;
  out.push(r);
}
await browser.close();

const pad = (s, n) => String(s).padEnd(n);
console.log(pad("风格", 14) + pad("空洞带", 24) + pad("二维码→文字带", 16) + pad("脚注下边距", 14) + "二维码");
let bad = 0;
for (const r of out) {
  const gapBad = r.qrGap !== null && r.qrGap < MIN_QR_GAP;
  const bottomBad = r.bottomGap < MIN_BOTTOM;
  const quietBad = r.qr.quiet < MIN_QR_QUIET;
  const moduleBad = r.qr.modulePx < MIN_QR_MODULE;
  const hostBad = !r.qr.hostOk;
  if (r.voids.length || gapBad || bottomBad || quietBad || moduleBad || hostBad) bad++;
  console.log(
    pad(r.style, 14) +
    pad(r.voids.length ? r.voids.map((x) => `${x.from}-${x.to}(${x.h})`).join(" ") : "—", 24) +
    pad(r.qrGap === null ? "—" : `${r.qrGap}px${gapBad ? " 太挤" : ""}`, 16) +
    pad(`${r.bottomGap}px${bottomBad ? " 贴边" : ""}`, 14) +
    `静区 ${r.qr.quiet.toFixed(1)} 模块${quietBad ? " 太窄" : ""} · ${r.qr.modulePx.toFixed(2)}px/模块${moduleBad ? " 太小" : ""} · ${r.qr.url.replace(/^https?:\/\//, "")}${hostBad ? " 站点不符" : ""}`,
  );
}
console.log(bad ? `\n${bad} 张卡存在排版或扫码问题` : "\n四张卡排版与扫码体检通过");
process.exit(bad ? 1 : 0);
