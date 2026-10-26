/**
 * 性能体检：先量后改。
 *
 * 这个作品的所有卖点都发生在 canvas 里，帧率、布局抖动、内存增长这类问题
 * 在截图上看不出来，只有量才知道。之前几轮靠肉眼估过两次（"FPS 实测 60"），
 * 但那是在没有 CPU 降速的桌面上测的 —— 中端手机上完全不是这个数。
 *
 * 指标与阈值（`BUDGET`）：
 *   - 首屏就绪：从导航开始到星图第一帧的时间
 *   - 帧预算：开场（1400 粒子最重）与稳态两段的 p50 / p95 帧间隔、长帧占比
 *   - 布局抖动：每帧同步调用 getBoundingClientRect / getComputedStyle 的次数
 *     （canvas 作品每帧读 DOM 几何 = 每次读都可能触发重排，最典型的性能坑）
 *   - 内存：8 秒稳态窗口的堆增长（每帧分配临时对象 → 堆一直涨 = 泄漏）
 *   - 分享卡导出：四张卡的耗时
 *   - 页面重量：总字节、外部请求数（单文件零依赖是这个项目的设计承诺）
 *
 * 用法：
 *   node scripts/perf_check.mjs                # 本地 demo/index.html，移动端降速 4x
 *   node scripts/perf_check.mjs --url http://...  # 指定地址
 *   node scripts/perf_check.mjs --json         # 机器可读输出
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const argv = process.argv.slice(2);
const has = (f) => argv.includes(f);
const optVal = (f, d) => {
  const i = argv.indexOf(f);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
};

const LOCAL = pathToFileURL(resolve("demo/index.html")).href;
const url = optVal("--url", LOCAL);
const asJson = has("--json");

// 预算。这些数字是"判断"，不是"实测值的复制"：60fps 每帧只有 16.7ms，
// 主线程留给绘制的时间必须显著低于它，否则合成器再快也会掉帧。
const BUDGET = {
  bootMs: 2500,
  introP50: 8,
  introP95: 16,
  steadyP50: 6,
  steadyP95: 12,
  // 每帧绘制调用数：arc 是最贵的那个（每颗粒子/星点一次）
  introArcs: 3600,
  steadyGrad: 2,
  rectPerFrame: 0.2,
  heapGrowthMB: 3,
  cardMs: 900,
  pageKB: 260,
  externalReqs: 0,
};

const PROFILES = [
  { name: "手机 390x844 @4x 降速", viewport: { width: 390, height: 844 }, isMobile: true, throttle: 4 },
  { name: "桌面 1440x900 不降速", viewport: { width: 1440, height: 900 }, isMobile: false, throttle: 1 },
];

/**
 * 探针必须在页面脚本之前注入。
 *
 * 关键取舍：**不测 rAF 的时间间隔**。无头 Chromium 没有 vsync，rAF 会以 160+Hz 空跑，
 * 量出来的"帧间隔 6ms / 164fps"和真实设备毫无关系（第一版探针就是这么被骗的）。
 * 改测两件真正属于我们代码成本的东西：
 *   1. 每帧主线程耗时（rAF 回调执行时长）—— 代码慢了它就涨，与显示器刷新率无关；
 *   2. 每帧 canvas 绘制调用数（arc / fill / stroke / 新建渐变）—— 完全确定性的数字，
 *      "每帧新建 9 个渐变"这种坑在帧率上看不出来，在这里一眼就看得见。
 */
const PROBE = () => {
  const p = (window.__perfProbe = { work: [], rect: 0, styled: 0, draw: null, frame: 0 });
  const blank = () => ({ arc: 0, fill: 0, stroke: 0, grad: 0, drawImage: 0 });
  p.draw = blank();
  const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) =>
    raf((t) => {
      p.frame++;
      const d0 = performance.now();
      const r = cb(t);
      p.work.push(Math.round((performance.now() - d0) * 100) / 100);
      return r;
    });
  const rect = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = function () {
    p.rect++;
    return rect.apply(this, arguments);
  };
  const gcs = window.getComputedStyle.bind(window);
  window.getComputedStyle = function () {
    p.styled++;
    return gcs.apply(window, arguments);
  };
  const C = CanvasRenderingContext2D.prototype;
  ["arc", "fill", "stroke", "drawImage"].forEach((k) => {
    const orig = C[k];
    C[k] = function () {
      p.draw[k]++;
      return orig.apply(this, arguments);
    };
  });
  ["createLinearGradient", "createRadialGradient"].forEach((k) => {
    const orig = C[k];
    C[k] = function () {
      p.draw.grad++;
      return orig.apply(this, arguments);
    };
  });
};

// 取一段窗口的"每帧"指标：把累计计数按窗口内的帧数均摊。
const perFrameDraw = (snapA, snapB, frames) => {
  const out = {};
  Object.keys(snapB).forEach((k) => {
    out[k] = frames > 0 ? Math.round(((snapB[k] - snapA[k]) / frames) * 100) / 100 : 0;
  });
  return out;
};

const pct = (arr, q) => {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(s.length * q))];
};

// 一段窗口里的每帧成本：p50 / p95 / 最大值（毫秒）
function workStats(arr) {
  if (!arr.length) return { n: 0, p50: 0, p95: 0, max: 0 };
  return {
    n: arr.length,
    p50: Math.round(pct(arr, 0.5) * 100) / 100,
    p95: Math.round(pct(arr, 0.95) * 100) / 100,
    max: Math.round(pct(arr, 1) * 100) / 100,
  };
}

async function measure(browser, profile) {
  const ctx = await browser.newContext({
    viewport: profile.viewport,
    isMobile: profile.isMobile,
    hasTouch: profile.isMobile,
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push("console: " + m.text());
  });
  await page.addInitScript(PROBE);
  if (profile.throttle > 1) {
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: profile.throttle });
  }

  const t0 = Date.now();
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
  // 首帧 = 星图数据已就位且 rAF 真的跑起来了
  await page.waitForFunction(() => window.__perfProbe && window.__perfProbe.work.length > 2, {
    timeout: 20000,
  });
  const bootMs = Date.now() - t0;

  const reset = () =>
    page.evaluate(() => {
      const p = window.__perfProbe;
      p.work.length = 0;
      p.frame = 0;
      p.draw = { arc: 0, fill: 0, stroke: 0, grad: 0, drawImage: 0 };
      p.rect = 0;
      p.styled = 0;
    });
  const snap = () =>
    page.evaluate(() => {
      const p = window.__perfProbe;
      return { work: p.work.slice(), frame: p.frame, draw: { ...p.draw }, rect: p.rect, styled: p.styled };
    });

  // 开场窗口：从首帧起 2000ms。此时仍在粒子拼字阶段（PHASE_TEXT=2600），
  // 上千颗粒子是这个作品最重的时刻。
  await reset();
  await page.waitForTimeout(2000);
  const introRaw = await snap();

  // 稳态窗口：必须等入场动画彻底结束（PHASE_TEXT 2600 + HOLD 1000 + FADE_START 1400
  // + FADE_DUR 1800 = 6800ms）之后。第一版只等了 3.2s，量到的还是"粒子正在淡出"，
  // 会把开场成本算进稳态（arc 726 其实全是残影）。
  await page.waitForTimeout(5600);
  await reset();
  await page.evaluate(() => {
    window.__heap0 = performance.memory ? performance.memory.usedJSHeapSize : null;
  });
  await page.waitForTimeout(3000);
  const steadyRaw = await snap();

  // 堆增长：稳态窗口之后再过 6 秒。绝对值说明不了问题，增长斜率才说明问题：
  // 每帧 new 一个临时对象 → 堆一直往上涨，低端机上迟早 GC 卡一下。
  await page.waitForTimeout(6000);
  const heap = await page.evaluate(() => ({
    h0: window.__heap0,
    h1: performance.memory ? performance.memory.usedJSHeapSize : null,
  }));

  const cardMs = await page.evaluate(() => {
    const mc = window.__mcuniverse;
    if (!mc) return null;
    const t = performance.now();
    ["deep", "nebula", "minimal", "achievement"].forEach((s) => mc.composeCard(s));
    return Math.round(performance.now() - t);
  });

  const pageBytes = readFileSync(decodeURIComponent(new URL(url).pathname.replace(/^\//, ""))).length;
  const res = await page.evaluate(() => performance.getEntriesByType("resource").map((r) => r.name));
  const external = res.filter((n) => !n.startsWith("data:") && !n.includes("/demo/"));

  await ctx.close();
  const zero = { arc: 0, fill: 0, stroke: 0, grad: 0, drawImage: 0 };
  return {
    profile: profile.name,
    bootMs,
    intro: workStats(introRaw.work),
    steady: workStats(steadyRaw.work),
    introDraw: perFrameDraw(zero, introRaw.draw, introRaw.frame),
    steadyDraw: perFrameDraw(zero, steadyRaw.draw, steadyRaw.frame),
    introFrames: introRaw.frame,
    steadyFrames: steadyRaw.frame,
    rectPerFrame: steadyRaw.frame ? Math.round((steadyRaw.rect / steadyRaw.frame) * 100) / 100 : 0,
    styledPerFrame: steadyRaw.frame ? Math.round((steadyRaw.styled / steadyRaw.frame) * 100) / 100 : 0,
    heapGrowthMB:
      heap.h0 != null && heap.h1 != null ? Math.round(((heap.h1 - heap.h0) / 1048576) * 10) / 10 : null,
    cardMs,
    pageKB: Math.round(pageBytes / 1024),
    externalReqs: external.length,
    external,
    errors,
  };
}

function judge(m) {
  const fail = [];
  const chk = (cond, msg) => {
    if (!cond) fail.push(msg);
  };
  chk(m.bootMs <= BUDGET.bootMs, `首屏 ${m.bootMs}ms > ${BUDGET.bootMs}ms`);
  chk(m.intro.p50 <= BUDGET.introP50, `开场 p50 ${m.intro.p50}ms > ${BUDGET.introP50}ms`);
  chk(m.intro.p95 <= BUDGET.introP95, `开场 p95 ${m.intro.p95}ms > ${BUDGET.introP95}ms`);
  chk(m.steady.p50 <= BUDGET.steadyP50, `稳态 p50 ${m.steady.p50}ms > ${BUDGET.steadyP50}ms`);
  chk(m.steady.p95 <= BUDGET.steadyP95, `稳态 p95 ${m.steady.p95}ms > ${BUDGET.steadyP95}ms`);
  chk(m.introDraw.arc <= BUDGET.introArcs, `开场每帧 ${m.introDraw.arc} 次 arc > ${BUDGET.introArcs}`);
  chk(m.steadyDraw.grad <= BUDGET.steadyGrad, `稳态每帧新建 ${m.steadyDraw.grad} 个渐变 > ${BUDGET.steadyGrad}`);
  chk(m.rectPerFrame <= BUDGET.rectPerFrame, `每帧 ${m.rectPerFrame} 次 getBoundingClientRect`);
  if (m.heapGrowthMB != null)
    chk(m.heapGrowthMB <= BUDGET.heapGrowthMB, `6s 堆增长 ${m.heapGrowthMB}MB > ${BUDGET.heapGrowthMB}MB`);
  chk(m.cardMs != null && m.cardMs <= BUDGET.cardMs, `四张分享卡 ${m.cardMs}ms > ${BUDGET.cardMs}ms`);
  chk(m.pageKB <= BUDGET.pageKB, `页面 ${m.pageKB}KB > ${BUDGET.pageKB}KB`);
  chk(m.externalReqs <= BUDGET.externalReqs, `外部请求 ${m.externalReqs} 个`);
  chk(m.errors.length === 0, `报错: ${m.errors.join("; ")}`);
  return fail;
}

const browser = await chromium.launch({ channel: "msedge" });
const results = [];
for (const p of PROFILES) {
  const m = await measure(browser, p);
  const fail = judge(m);
  results.push({ ...m, fail });
  if (!asJson) {
    const d = (x) => `arc ${x.arc} fill ${x.fill} stroke ${x.stroke} 渐变 ${x.grad}`;
    console.log(`\n▌${m.profile}`);
    console.log(`  首屏 ${m.bootMs}ms | 开场每帧 ${m.intro.p50}ms (p95 ${m.intro.p95}, 最慢 ${m.intro.max})`);
    console.log(`  稳态每帧 ${m.steady.p50}ms (p95 ${m.steady.p95}, 最慢 ${m.steady.max})`);
    console.log(`  绘制/帧 开场 ${d(m.introDraw)}`);
    console.log(`  绘制/帧 稳态 ${d(m.steadyDraw)}`);
    console.log(
      `  每帧 rect ${m.rectPerFrame} / style ${m.styledPerFrame} | 堆增长 ${m.heapGrowthMB}MB | ` +
        `四卡 ${m.cardMs}ms | 页面 ${m.pageKB}KB / 外部请求 ${m.externalReqs}`,
    );
    if (fail.length) fail.forEach((f) => console.log(`  ✗ ${f}`));
    else console.log("  ✓ 全部达标");
  }
}
await browser.close();

if (asJson) console.log(JSON.stringify(results, null, 2));
const bad = results.reduce((n, r) => n + r.fail.length, 0);
if (!asJson) console.log(bad ? `\n${bad} 项超标` : "\n性能体检 PASS");
process.exit(bad ? 1 : 0);
