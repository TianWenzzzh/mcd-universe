/**
 * E2E 冒烟检查：用真实浏览器打开演示页，验证
 * 1. 页面无控制台错误 / 未捕获异常
 * 2. 星点已渲染
 * 3. 分享卡 composeCard() 产出合法 1080x1440 PNG（落盘供人工查看），四种风格全覆盖
 * 4. 五态（银河 / 星云 / 甜点 / 减少动效 / 移动端银河）均可打开
 * 5. 交互级断言：导出面板真实点击、键盘浏览、悬停气泡、aria-live、导航入口
 * 6. 移动端 HUD 布局矩形两两不重叠
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
  // 触屏参数必须真的传给 newPage：只给 viewport 的话 (pointer: coarse) 仍然为 false，
  // 页面会走鼠标分支 —— 那这条触屏断言就成了"看着跑了、其实没测"。
  const ctxOpts = { viewport: opts.viewport };
  if (opts.isMobile) { ctxOpts.isMobile = true; ctxOpts.hasTouch = true; }
  if (opts.deviceScaleFactor) ctxOpts.deviceScaleFactor = opts.deviceScaleFactor;
  const page = await browser.newPage(ctxOpts);
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
    // 导出走的是"临时把舞台重排成竖版卡片构图"的路子：导完必须把屏幕上的星群摆回原位，
    // 否则用户会看到星图凭空变形（本项目的经典复发 bug 类型：副作用泄漏回主视图）。
    const before = await page.evaluate(() =>
      window.__mcuniverse.stars.map((s) => [Math.round(s.bx), Math.round(s.by)]),
    );
    const cards = await page.evaluate(() => {
      return ["deep", "nebula", "minimal", "achievement"].map((style) => {
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
      if (card.style === "achievement") writeFileSync(`${OUT_DIR}/share-card-achievement.png`, Buffer.from(b64, "base64"));
    }
    state.cardBytes = Object.values(state.cards).join("/");

    // 卡片几何：直接读 cardLayout() 规格算，不靠像素（星场随机星会干扰像素判定）。
    // 这条管的是"换个更长的文案就撞车""脚注被平台圆角切掉"这类只在真实数据下才暴露的问题。
    const geo = await page.evaluate(() => {
      const mc = window.__mcuniverse;
      const out = [];
      const desc = mc.data.persona ? mc.data.persona.desc : "";
      for (const style of ["deep", "nebula", "minimal", "achievement"]) {
        const L = mc.cardLayout(style);
        const q = L.qr;
        const problems = [];
        const SAFE = 48;
        if (q.x + q.size > 1080 - SAFE) problems.push(`二维码右边距 ${1080 - q.x - q.size}px`);
        if (q.y + q.size > 1440 - SAFE) problems.push(`二维码下边距 ${1440 - q.y - q.size}px`);
        const footGap = 1440 - (L.footer + L.footerSize * 0.25);
        if (footGap < SAFE) problems.push(`脚注下边距 ${Math.round(footGap)}px`);
        if (q.label && q.label + 4 > q.y) problems.push("二维码说明压在码上");
        if (L.desc) {
          // 描述按实际文案断行，最后一行必须落在脚注上方，且不能伸到二维码那一列
          const lines = mc.wrapLines(desc, L.desc.maxW, L.desc.size);
          const lastBase = L.desc.y + (lines.length - 1) * L.desc.lh;
          const lastFoot = lastBase + L.desc.size * 0.25;
          if (lastFoot > L.footer - L.footerSize * 0.9) {
            problems.push(`描述最后一行(${Math.round(lastFoot)})压到脚注(${L.footer})`);
          }
          if (lines.length > 3) problems.push(`描述断成 ${lines.length} 行，超出卡片预留高度`);
          for (const t of lines) {
            if (/^[，。、；：！？）】》”’%]/.test(t)) problems.push(`行首挂了标点: ${t}`);
            const w = (() => {
              const c = document.createElement("canvas").getContext("2d");
              c.font = L.desc.size + "px -apple-system, PingFang SC, sans-serif";
              return c.measureText(t).width;
            })();
            if (w > L.desc.maxW + 1) problems.push(`行宽 ${Math.round(w)} 超出版心 ${L.desc.maxW}: ${t}`);
          }
          if (q.x > 540 && 540 + L.desc.maxW / 2 > q.x - 16) problems.push("描述版心伸进了二维码那一列");
        }
        out.push({ style, lines: L.desc ? mc.wrapLines(desc, L.desc.maxW, L.desc.size).length : 0, problems });
      }
      return out;
    });
    state.geo = geo.map((g) => `${g.style}:${g.lines}行`).join(" ");
    for (const g of geo) for (const p of g.problems) problems.push(`${g.style} 版式: ${p}`);

    const after = await page.evaluate(() =>
      window.__mcuniverse.stars.map((s) => [Math.round(s.bx), Math.round(s.by)]),
    );
    if (JSON.stringify(before) !== JSON.stringify(after)) {
      problems.push("导出分享卡后屏幕构图未复位（卡片竖版布局泄漏到了主视图）");
    }
  }
  if (opts.ui) {
    // 桌面端引导文案要讲鼠标与键盘（跟触屏版互为对照，防止"两边都写死成同一套"）
    const deskStep2 = await page.evaluate(() => {
      const el = document.getElementById("ob-step2");
      return el ? el.textContent : "";
    });
    if (!/悬停|滚轮/.test(deskStep2)) problems.push(`桌面引导文案缺鼠标动作: ${deskStep2}`);
    // 导航闭环：首访引导里必须有通往作品说明页的入口
    const obLink = await page.evaluate(() => {
      const a = document.querySelector(".ob-tip a");
      return a ? a.getAttribute("href") : null;
    });
    if (!obLink || !obLink.includes("docs/about.html")) problems.push("首访引导缺少作品说明入口");
    // 当前人格页要在切换器里被标出来：视觉 .cur 之外还要有语义 aria-current
    const ariaCur = await page.evaluate(() => {
      const a = document.querySelector('#switcher a[aria-current="page"]');
      return a ? a.getAttribute("href") : null;
    });
    if (ariaCur !== "./") problems.push(`切换器 aria-current 缺失或错位: ${ariaCur}`);
    // 首访引导会拦截点击：先关掉（同时验证引导层可关闭）
    await page.evaluate(() => window.__mcuniverse.dismissOnboard());
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
    if (previewCount !== 4) problems.push(`风格预览应为 4 张，实际绘出 ${previewCount}`);
    // 焦点应进入面板，且在四个风格按钮之间循环（focus trap）
    const focusFirst = await page.evaluate(() =>
      document.activeElement ? document.activeElement.getAttribute("data-style") : null,
    );
    if (focusFirst !== "deep") problems.push(`打开面板后焦点未进入面板: ${focusFirst}`);
    for (let i = 0; i < 4; i++) await page.keyboard.press("Tab");
    const wrapped = await page.evaluate(() =>
      document.activeElement ? document.activeElement.getAttribute("data-style") : null,
    );
    if (wrapped !== "deep") problems.push(`面板焦点未在四格间循环（Tab 4 次落到 ${wrapped}）`);
    const downloadPromise = page.waitForEvent("download", { timeout: 15000 }).catch(() => null);
    await page.click('.ep-style[data-style="minimal"]');
    const dl = await downloadPromise;
    if (!dl) problems.push("点击风格后未触发下载");
    else state.download = dl.suggestedFilename();

    // Esc：关闭面板并把焦点交还给触发按钮
    await page.click("#btn-save");
    await page.waitForTimeout(400);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    const escState = await page.evaluate(() => ({
      closed: !document.getElementById("export-panel").classList.contains("show"),
      focus: document.activeElement ? document.activeElement.id : null,
    }));
    if (!escState.closed) problems.push("Esc 未关闭导出面板");
    if (escState.focus !== "btn-save") problems.push(`Esc 后焦点未回到触发按钮: ${escState.focus}`);

    // 键盘：方向键逐颗浏览，详情面板应展开
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
  if (opts.touch) {
    // 触屏专项：文案、布局、手势三件事都必须按"没有鼠标"的现实来
    const t = await page.evaluate(() => {
      const ob = document.getElementById("ob-step2");
      const lg = document.getElementById("legend");
      const lr = lg.getBoundingClientRect();
      return {
        coarse: window.__mcuniverse.coarse,
        step2: ob ? ob.textContent : "",
        legendDir: getComputedStyle(lg).flexDirection,
        legendH: Math.round(lr.height),
        touchAction: getComputedStyle(document.getElementById("sky")).touchAction,
      };
    });
    if (!t.coarse) problems.push("触屏环境未识别为 coarse pointer（文案会退回鼠标版）");
    if (!/轻点|点按|捏合/.test(t.step2)) problems.push(`触屏引导文案没有触屏动作: ${t.step2}`);
    if (/悬停|滚轮|键盘/.test(t.step2)) problems.push(`触屏引导文案仍在讲鼠标/键盘: ${t.step2}`);
    if (t.legendDir !== "row") problems.push(`竖屏图例未改横排（${t.legendDir}），会占掉纵向空间`);
    if (t.legendH > 76) problems.push(`竖屏图例高度 ${t.legendH}px 超过两行预算`);
    if (t.touchAction !== "none") problems.push(`画布 touch-action=${t.touchAction}，双指手势会被浏览器截走`);

    // 星点不许钻进 HUD 底下：把整圈旋转角扫一遍，任何角度下星心落在 HUD 矩形内都算失败
    // （卡片不透明，钻进去=那颗星凭空消失）。这比截一张图可信，因为它覆盖所有角度。
    const hidden = await page.evaluate(() => {
      const ids = ["title", "legend", "persona", "actions", "stats", "demo-badge", "switcher"];
      const rects = ids.map((id) => {
        const el = document.getElementById(id);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return r.height > 1 ? { id, t: r.top, b: r.bottom, l: r.left, r: r.right } : null;
      }).filter(Boolean);
      const out = {};
      for (let a = 0; a < Math.PI * 2; a += 0.08) {
        for (const s of window.__mcuniverse.stars) {
          const an = s.ang + a;
          const cx = s.bx - Math.cos(s.ang) * s.ex * s.k;
          const cy = s.by - Math.sin(s.ang) * s.ey * s.k;
          const px = cx + Math.cos(an) * s.ex * s.k;
          const py = cy + Math.sin(an) * s.ey * s.k;
          for (const rc of rects) {
            if (px > rc.l && px < rc.r && py > rc.t && py < rc.b) out[rc.id] = (out[rc.id] || 0) + 1;
          }
        }
      }
      return out;
    });
    if (Object.keys(hidden).length) {
      problems.push("星点会钻到 HUD 底下: " + JSON.stringify(hidden));
    }

    // 双指捏合：手机上唯一的缩放入口，走真实 pointer 事件链
    const z0 = await page.evaluate(() => window.__mcuniverse.zoom());
    const z1 = await page.evaluate(() => {
      const cv = document.getElementById("sky");
      const mk = (type, id, x, y) => new PointerEvent(type, {
        pointerId: id, clientX: x, clientY: y, bubbles: true, pointerType: "touch", isPrimary: id === 1,
      });
      cv.dispatchEvent(mk("pointerdown", 1, 150, 300));
      cv.dispatchEvent(mk("pointerdown", 2, 250, 300));
      cv.dispatchEvent(mk("pointermove", 1, 100, 300));
      cv.dispatchEvent(mk("pointermove", 2, 300, 300));
      const z = window.__mcuniverse.zoom();
      cv.dispatchEvent(mk("pointerup", 1, 100, 300));
      cv.dispatchEvent(mk("pointerup", 2, 300, 300));
      return z;
    });
    if (!(z1 > z0 * 1.3)) problems.push(`双指捏合未缩放: ${z0} -> ${z1}`);
    state.pinch = `${z0}->${z1}`;
  }
  if (opts.overlapCheck) {
    // HUD 互相压叠是这个项目反复复发的一类 bug（按钮被画布盖、徽章压副标、切换器重叠）。
    // 这里量真实布局矩形，任何两块可见 HUD 有 >2px 交集都算失败。
    const hits = await page.evaluate(() => {
      // detail / tip / toast 是按需弹出的浮层，允许盖住别的 HUD，不参与判定
      const ids = ["title", "demo-badge", "switcher", "stats", "daily", "legend", "persona", "actions"];
      const boxes = [];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        const st = getComputedStyle(el);
        if (st.display === "none" || st.visibility === "hidden" || parseFloat(st.opacity) === 0) continue;
        const r = el.getBoundingClientRect();
        if (r.width > 1 && r.height > 1) boxes.push({ id, top: r.top, bottom: r.bottom, left: r.left, right: r.right });
      }
      const out = [];
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          const a = boxes[i], b = boxes[j];
          const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
          const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
          if (ox > 2 && oy > 2) out.push(`${a.id}×${b.id} 重叠 ${Math.round(ox)}×${Math.round(oy)}px`);
        }
      }
      return out;
    });
    problems.push(...hits);
    state.hudBoxes = hits.length;
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
      isMobile: true,
      hasTouch: true,
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
  // 移动端银河态：HUD 元素多，是重叠 bug 的高发区；hasTouch 让页面真的走触屏分支
  results.push(
    await checkPage(browser, BASE + "?e2e=1&mobile=1", {
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      expectNebula: false,
      expectStars: 10,
      overlapCheck: true,
      touch: true,
    }),
  );
  // 小屏（360x640）：可用纵向空间最紧张的一档，星群最容易挤爆或钻到 HUD 底下
  results.push(
    await checkPage(browser, BASE + "?e2e=1&small=1", {
      viewport: { width: 360, height: 640 },
      isMobile: true,
      hasTouch: true,
      expectNebula: false,
      expectStars: 10,
      overlapCheck: true,
      touch: true,
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
    if (r.state.pinch) console.log(`     pinch=${r.state.pinch}`);
    r.problems.forEach((p) => console.log("     - " + p));
  }
  process.exit(failed ? 1 : 0);
}

main().catch((e) => {
  console.error("E2E 运行失败:", e);
  process.exit(1);
});
