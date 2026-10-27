/**
 * 说明页版式体检：量「作品截图」格子的空洞与对齐。
 *
 * 为什么需要它：这个格子是 CSS Grid 两列，四张截图的宽高比完全不同
 * （16:10 桌面 / 9:19.5 手机 / 3:4 分享卡 / 16:10 导出面板）。
 * grid 默认 align-items: stretch，一行的高度由最高的那张决定，
 * 矮图就被拉成一张巨大的空卡片，图注沉到卡片底部 —— 肉眼缩到 0.36 倍
 * 看全页时几乎看不出来，只有在页面上滚动时才会觉得「这里怎么空了一大块」。
 *
 * 量三件事：
 *   1. 内部空洞：卡片下沿 - 图注下沿（>GAP_MAX 视为空洞）。
 *      注意这里不能量「图注上沿 - 图片下沿」—— 那永远是 0，因为图注紧跟在图片后面，
 *      被拉伸出来的空白全部落在图注**下面**。第一版量具就是量错了这个位置，
 *      于是给了个假 PASS（卡片 917px、图片 254px 竟然"没有空洞"），别重犯。
 *   2. 同行对齐：同一行里最高与最矮卡片的差（>ROW_MAX 视为不齐）
 *   3. 横向溢出：文档宽度是否超过视口
 *
 * 用法：
 *   node scripts/layout_audit.mjs                      # 本地 docs/about.html，三档宽度
 *   node scripts/layout_audit.mjs <baseUrl>            # 指定站点根（如线上 Pages）
 *   node scripts/layout_audit.mjs <baseUrl> --json
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const GAP_MAX = 24; // 图注与图片之间允许的最大空白（也就是空洞阈值）
const ROW_MAX = 12; // 同一行卡片高度允许的差值
const WIDTHS = [
  { name: "桌面 1440", w: 1440, h: 900, mobile: false },
  { name: "中屏 820", w: 820, h: 1180, mobile: false },
  { name: "手机 390", w: 390, h: 844, mobile: true },
];

const args = process.argv.slice(2);
const asJson = args.includes("--json");
const base = (args.find((a) => !a.startsWith("--")) || "http://127.0.0.1:8811").replace(/\/$/, "");
const url = `${base}/docs/about.html`;

const browser = await chromium.launch({ channel: "msedge" });
const report = [];

for (const vp of WIDTHS) {
  const page = await browser.newPage({
    viewport: { width: vp.w, height: vp.h },
    deviceScaleFactor: 1,
    isMobile: vp.mobile,
    hasTouch: vp.mobile,
  });
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  // 图片是 lazy 的：全页滚一遍逼它们进入视口，再等 network idle + 全部 decode 完。
  // 只等固定毫秒数在线上（Pages 首字节不慢但图片是逐个拉的）会读到 naturalHeight=0，
  // 于是本机 PASS、线上全报"未加载" —— 量具的等待必须等"条件"，不是等"时间"。
  await page.evaluate(async () => {
    const step = window.innerHeight;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForLoadState("networkidle").catch(() => {});
  await page
    .waitForFunction(
      () => [...document.querySelectorAll(".shots img, .grid2 img")].every((i) => i.complete && i.naturalHeight > 0),
      null,
      { timeout: 15000 },
    )
    .catch(() => {});
  await page.waitForTimeout(200);

  const m = await page.evaluate(() => {
    const figs = [...document.querySelectorAll(".shots figure, .grid2 figure")];
    const items = figs.map((f, i) => {
      const fr = f.getBoundingClientRect();
      const img = f.querySelector("img");
      const cap = f.querySelector("figcaption");
      // 量的是 img 的**布局盒**：getBoundingClientRect 会算上 transform，
      // 而「导出面板」那张套了 scale(1.5) 取中，rect 会把 346px 读成 520px，
      // 于是被误判成"卡片被压塌"。优先量外层的 .shot-frame（不缩放），退回 offsetHeight。
      const box = f.querySelector(".shot-frame");
      const ih = box ? box.getBoundingClientRect().height : img ? img.offsetHeight : 0;
      const ir = img && ih ? { height: ih } : null;
      const cr = cap ? cap.getBoundingClientRect() : null;
      return {
        i,
        top: Math.round(fr.top + window.scrollY),
        h: Math.round(fr.height),
        imgH: ir ? Math.round(ir.height) : 0,
        // 卡片高度 - 图片高度 - 图注高度 = 卡片里真正空着的那块（不关心它落在图上还是图下）
        voidPx: ir && cr ? Math.round(fr.height - ir.height - cr.height - 2) : 0,
        // 图片没加载出来时（naturalHeight 为 0）要单独报，否则会被当成"没有空洞"
        loaded: !!(img && img.naturalHeight > 0),
        src: img ? img.getAttribute("src") : "",
      };
    });
    // 按视觉行分组：top 相差不到 4px 算同一行
    const rows = [];
    for (const it of items) {
      const row = rows.find((r) => Math.abs(r[0].top - it.top) < 4);
      if (row) row.push(it);
      else rows.push([it]);
    }
    return {
      items,
      rows: rows.map((r) => ({
        tops: r.map((x) => x.top),
        heights: r.map((x) => x.h),
        spread: Math.max(...r.map((x) => x.h)) - Math.min(...r.map((x) => x.h)),
      })),
      docW: document.documentElement.scrollWidth,
      vw: document.documentElement.clientWidth,
      cols: figs.length ? getComputedStyle(figs[0].parentElement).flexDirection : "",
    };
  });
  await page.close();

  const problems = [];
  for (const it of m.items) {
    if (!it.loaded) problems.push(`图 ${it.i + 1} 未加载（${it.src}）`);
    // 负值 = 卡片比内容还矮，图片正溢出到卡片外（flex-basis:0 落进纵向容器就是这么塌的）。
    // 这种"卡片高 2px"在只判"空洞 ≤ 阈值"的量具下是 PASS —— 必须单独当错误报。
    if (it.voidPx < -2) problems.push(`图 ${it.i + 1} 卡片被压塌：内容高 ${it.imgH}px，卡片只剩 ${it.h}px`);
    if (it.voidPx > GAP_MAX) problems.push(`图 ${it.i + 1} 卡片内部空洞 ${it.voidPx}px（阈值 ${GAP_MAX}）`);
  }
  m.rows.forEach((r, i) => {
    if (r.spread > ROW_MAX) problems.push(`第 ${i + 1} 行卡片高度差 ${r.spread}px（阈值 ${ROW_MAX}）`);
  });
  if (m.docW > m.vw + 1) problems.push(`横向溢出：文档 ${m.docW}px > 视口 ${m.vw}px`);

  report.push({ viewport: vp.name, items: m.items, rows: m.rows, docW: m.docW, vw: m.vw, problems });
}

await browser.close();

if (asJson) {
  console.log(JSON.stringify(report, null, 2));
} else {
  for (const r of report) {
    console.log(`\n▌${r.viewport}`);
    for (const it of r.items) {
      console.log(
        `  图 ${it.i + 1}  卡片高 ${String(it.h).padStart(4)}px  图片高 ${String(it.imgH).padStart(4)}px  内部空洞 ${String(it.voidPx).padStart(4)}px`,
      );
    }
    r.rows.forEach((row, i) => console.log(`  第 ${i + 1} 行 卡片高 [${row.heights.join(", ")}] 差 ${row.spread}px`));
  }
  const bad = report.filter((r) => r.problems.length);
  console.log("");
  if (bad.length) {
    console.log(`版式体检失败（${bad.reduce((n, r) => n + r.problems.length, 0)} 项）`);
    for (const r of bad) for (const p of r.problems) console.log(`  ✗ ${r.viewport}: ${p}`);
  } else {
    console.log(`PASS 说明页版式体检（${report.length} 档宽度，空洞 ≤${GAP_MAX}px、行高差 ≤${ROW_MAX}px、无横向溢出）`);
  }
}

process.exit(report.some((r) => r.problems.length) ? 1 : 0);
