/**
 * E2E 冒烟检查：用真实浏览器打开演示页，验证
 * 1. 页面无控制台错误 / 未捕获异常
 * 2. 星点已渲染
 * 3. 分享卡 composeCard() 产出合法 1080x1440 PNG（落盘供人工查看），四种风格全覆盖
 * 4. 六态（银河 / 星云 / 甜点 / 减少动效 / 移动端银河 / 小屏）均可打开
 * 5. 交互级断言：导出面板真实点击、键盘浏览、悬停气泡、aria-live、导航入口
 * 6. 移动端 HUD 布局矩形两两不重叠
 * 7. 分享卡交付路径：微信内必须走"预览 + 长按保存"（微信不实现 a[download]），
 *    普通浏览器必须走下载；两种路径的提示文案不许混用
 * 8. 六层浮层（引导 / 预览 / 导出 / 导入 / 成就 / 更多）都是真模态：role、焦点进入、Tab 循环、Esc 关闭
 * 9. 引导层弹出时机：普通模式等粒子入场放完，减少动效模式不等
 * 10. 深链 ?open=import：落地直接开面板，且不得再排首访引导
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

// 微信内置浏览器不实现 a[download] + data: URL，但"安卓系统浏览器"实现 ——
// 同一台设备两种容器，交付路径必须不同，所以要用真实 UA 分别跑。
const UA_WECHAT_ANDROID = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) " +
  "Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0.42.2460(0x28002A33) " +
  "WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64";
const UA_IOS_SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 " +
  "(KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1";
// 同一台安卓手机的系统浏览器：它实现 a[download]，交付路径必须回到下载
const UA_CHROME_ANDROID = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36";

async function checkPage(browser, url, opts) {
  // 触屏参数必须真的传给 newPage：只给 viewport 的话 (pointer: coarse) 仍然为 false，
  // 页面会走鼠标分支 —— 那这条触屏断言就成了"看着跑了、其实没测"。
  const ctxOpts = { viewport: opts.viewport };
  if (opts.isMobile) { ctxOpts.isMobile = true; ctxOpts.hasTouch = true; }
  if (opts.deviceScaleFactor) ctxOpts.deviceScaleFactor = opts.deviceScaleFactor;
  if (opts.ua) ctxOpts.userAgent = opts.ua;
  const page = await browser.newPage(ctxOpts);
  const problems = [];
  page.on("console", (m) => {
    if (m.type() === "error") problems.push("console: " + m.text());
  });
  page.on("pageerror", (e) => problems.push("pageerror: " + String(e)));
  if (opts.reducedMotion) await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
  // 引导层弹出时机要"两头卡"：普通模式必须等粒子入场放完（提前弹是打断），
  // 减少动效模式没有动画可等，必须很快弹（曾经一律等 5.2 秒 = 对着静态星图白站 5 秒）。
  let onboardAt = 0;
  if (opts.onboardDeadline) {
    const t0 = Date.now();
    const appeared = await page.waitForSelector("#onboard.show", { timeout: opts.onboardDeadline })
      .then(() => true).catch(() => false);
    onboardAt = Date.now() - t0;
    if (!appeared) problems.push(`首访引导 ${opts.onboardDeadline}ms 内没弹出`);
    else if (opts.onboardMin && onboardAt < opts.onboardMin) {
      problems.push(`引导弹得太早（${onboardAt}ms），粒子入场还在放`);
    }
  }
  await page.waitForTimeout(4500);
  const state = await page.evaluate(() => {
    const mc = window.__mcuniverse;
    return {
      stars: mc ? mc.stars.length : -1,
      isNebula: mc ? mc.isNebula : null,
      reduced: mc ? mc.reduced : null,
      persona: mc && mc.data.persona ? mc.data.persona.name : null,
      textTargets: mc && mc.textTargets ? mc.textTargets : null,
    };
  });
  // 文字目标必须覆盖完整字形。手机 390 屏上字号约 85px，正常 y 跨度 ~55px；
  // 旧实现只取采样点前缀，y 跨度只有十几像素，肉眼就是四条横带。
  if (!state.isNebula && state.textTargets && (state.textTargets.y < 30 || state.textTargets.x < 100)) {
    problems.push(`粒子文字目标覆盖不足: ${Math.round(state.textTargets.x)}×${Math.round(state.textTargets.y)}`);
  }
  if (onboardAt) state.onboardAt = onboardAt;

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
  // 孤悬行检测：换行排布最容易留下"最后一行只剩一颗"，看上去像没做完。
  // 图例曾在手机上排成 5+1；判定按几何位置分组而不看 CSS 实现。
  const rows = await page.evaluate(() => {
    const rowsOf = (sel) => {
      const m = {};
      [...document.querySelectorAll(sel)].forEach((el) => {
        const cs = getComputedStyle(el);
        if (cs.display === "none" || cs.visibility === "hidden") return;
        const t = Math.round(el.getBoundingClientRect().top);
        m[t] = (m[t] || 0) + 1;
      });
      return Object.keys(m)
        .sort((a, b) => a - b)
        .map((k) => m[k]);
    };
    return { legend: rowsOf("#legend > span") };
  });
  state.rows = rows;
  for (const [name, list] of Object.entries(rows)) {
    const mixed = list.slice(0, -1).some((n) => n > 1);
    if (list.length > 1 && list[list.length - 1] === 1 && mixed) {
      problems.push(`${name} 最后一行只剩 1 项（${list.join("+")}），是孤悬行`);
    }
  }

  if (opts.dialogs) {
    // 浮层必须是真模态。这个项目吃过"看不见的控件在响应"的亏（#actions 按钮曾是死的、
    // 引导层背后 Tab 能落到画布上）—— 遮罩挡住鼠标，键盘却照样穿过去，是最难被发现的一类。
    await page.waitForSelector("#onboard.show", { timeout: 15000 }).catch(() => null);
    const dlg = await page.evaluate(() => {
      const ob = document.getElementById("onboard");
      return {
        shown: ob.classList.contains("show"),
        role: ob.getAttribute("role"),
        modal: ob.getAttribute("aria-modal"),
        focusInside: ob.contains(document.activeElement),
        focusId: document.activeElement ? document.activeElement.id || document.activeElement.tagName : null,
      };
    });
    if (!dlg.shown) problems.push("首访引导没有出现");
    if (dlg.role !== "dialog" || dlg.modal !== "true") {
      problems.push(`引导层缺对话框语义: role=${dlg.role} aria-modal=${dlg.modal}`);
    }
    if (!dlg.focusInside) problems.push(`引导层弹出后焦点仍在遮罩背后: ${dlg.focusId}`);
    let escaped = null;
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("Tab");
      const where = await page.evaluate(() => ({
        inside: document.getElementById("onboard").contains(document.activeElement),
        id: document.activeElement ? document.activeElement.id || document.activeElement.tagName : null,
      }));
      if (!where.inside) { escaped = where.id; break; }
    }
    if (escaped) problems.push(`引导层 Tab 逃到遮罩背后: ${escaped}（不是真模态）`);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
    const obClosed = await page.evaluate(() => !document.getElementById("onboard").classList.contains("show"));
    if (!obClosed) problems.push("Esc 未关闭首访引导");
    // 关掉后焦点不许留在已隐藏的层里（否则下一次 Tab 从文档开头重来）
    const obFocus = await page.evaluate(() => ({
      hiddenFocused: document.getElementById("onboard").contains(document.activeElement),
    }));
    if (obFocus.hiddenFocused) problems.push("引导关闭后焦点留在了隐藏层内");
  }
  if (opts.delivery) {
    // 分享卡的最后一公里：微信里 a[download] 是空操作，而提示若还写"已导出"，
    // 用户以为存好了，其实相册里什么都没有 —— 分享链就此断在这里。
    await page.evaluate(() => window.__mcuniverse.dismissOnboard());
    await page.waitForTimeout(250);
    const saveMode = await page.evaluate(() => window.__mcuniverse.saveMode());
    state.saveMode = saveMode;
    if (saveMode !== opts.delivery) problems.push(`交付路径应为 ${opts.delivery}，实际 ${saveMode}`);
    await page.click("#btn-save");
    await page.waitForTimeout(700);
    // 面板上"点击即导出"这句话在微信里是假话，必须换成"生成后长按保存"
    const panelTip = await page.evaluate(() => (document.querySelector(".ep-tip") || {}).textContent || "");
    if (opts.delivery === "preview" && !/长按/.test(panelTip)) {
      problems.push(`导出面板仍在承诺下载（微信里不会发生）: ${panelTip}`);
    }
    if (opts.delivery === "download" && /长按/.test(panelTip)) {
      problems.push(`下载容器却提示长按保存: ${panelTip}`);
    }
    // 先挂上下载监听再点：微信路径下这里必须"等不到"下载事件
    const dlPromise = page.waitForEvent("download", { timeout: 3000 }).catch(() => null);
    await page.click('.ep-style[data-style="deep"]');
    const dl = await dlPromise;
    await page.waitForTimeout(350);
    const after = await page.evaluate(() => ({
      preview: document.getElementById("img-preview").classList.contains("show"),
      toast: document.getElementById("toast").textContent,
      tip: (document.querySelector(".ip-card .ip-tip") || {}).textContent || "",
      role: document.getElementById("img-preview").getAttribute("role"),
      modal: document.getElementById("img-preview").getAttribute("aria-modal"),
      focus: document.activeElement ? document.activeElement.id || document.activeElement.tagName : null,
      live: document.getElementById("a11y-live").textContent,
      src: (document.querySelector(".ip-card img") || {}).src || "",
    }));
    if (opts.delivery === "preview") {
      if (dl) problems.push(`微信/iOS 内仍走了下载路径（${dl.suggestedFilename()}）：微信不实现 a[download]，等于点了没反应`);
      if (!after.preview) problems.push("微信/iOS 内点导出后未弹出长按保存层（分享卡无处可存）");
      if (!/^data:image\/png/.test(after.src)) problems.push("预览层里的图片不是生成的分享卡");
      if (!/长按/.test(after.tip)) problems.push(`保存提示没讲长按: ${after.tip}`);
      if (opts.wechatHint && !/浏览器/.test(after.tip)) problems.push(`微信内提示没给"换浏览器"兜底: ${after.tip}`);
      if (!opts.wechatHint && /浏览器/.test(after.tip)) problems.push(`非微信容器不该提换浏览器: ${after.tip}`);
      if (/已导出/.test(after.toast)) problems.push(`预览路径却谎报「已导出」: ${after.toast}`);
      if (after.role !== "dialog" || after.modal !== "true") {
        problems.push(`预览层缺对话框语义: role=${after.role} aria-modal=${after.modal}`);
      }
      if (after.focus !== "ip-close") problems.push(`预览层焦点未进入: ${after.focus}`);
      if (!/保存/.test(after.live)) problems.push(`读屏未播报保存方式: ${after.live}`);
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
      const closed = await page.evaluate(() => ({
        open: document.getElementById("img-preview").classList.contains("show"),
        focus: document.activeElement ? document.activeElement.id || document.activeElement.tagName : null,
      }));
      if (closed.open) problems.push("Esc 未关闭预览层");
      if (closed.focus !== "btn-save") problems.push(`关掉预览层后焦点未回到保存按钮: ${closed.focus}`);
    } else {
      if (after.preview) problems.push("普通浏览器不该弹长按保存层");
      if (!dl) problems.push("普通浏览器点导出未触发下载");
      else state.download = dl.suggestedFilename();
      if (/长按/.test(after.toast)) problems.push(`下载路径的提示串成了长按文案: ${after.toast}`);
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
    // 首屏主 CTA 必须真的是「粘贴订单」，样例切换收在一个 select 里。
    const hero = await page.evaluate(() => {
      const cta = document.getElementById("import-open");
      const sample = document.getElementById("sample-select");
      const box = cta ? cta.getBoundingClientRect() : null;
      return {
        text: cta ? cta.textContent.trim() : null,
        visible: !!(box && box.width > 160 && box.height >= 40),
        sample: sample ? sample.value : null,
        sampleVisible: sample ? getComputedStyle(document.getElementById("sample-row")).display !== "none" : false,
      };
    });
    if (!hero.text || !hero.text.includes("粘贴订单")) problems.push(`首屏主 CTA 文案错误: ${hero.text}`);
    if (!hero.visible) problems.push("首屏主 CTA 不可见或尺寸过小");
    if (hero.sample !== "./") problems.push(`样例选择器值错误: ${hero.sample}`);
    if (!hero.sampleVisible) problems.push("演示页没有显示样例选择器");
    // 首访引导会拦截点击：先关掉（同时验证引导层可关闭）
    await page.evaluate(() => window.__mcuniverse.dismissOnboard());
    await page.waitForTimeout(200);

    // 成就列表：必须真是列表、有进度、且包含用户点名的「汉堡王」。
    await page.click("#btn-ach");
    await page.waitForTimeout(350);
    const ach = await page.evaluate(() => {
      const panel = document.getElementById("ach-panel");
      const items = [...document.querySelectorAll("#ach-list .ach-item")];
      return {
        open: panel.classList.contains("show"),
        count: items.length,
        unlocked: items.filter((el) => el.classList.contains("unlocked")).length,
        hasBurgerKing: items.some((el) => el.textContent.includes("汉堡王")),
        hasProgress: items.some((el) => el.querySelector(".bar i") !== null),
        focusInside: panel.contains(document.activeElement),
      };
    });
    if (!ach.open) problems.push("成就面板未打开");
    if (ach.count !== 10) problems.push(`成就列表应为 10 项，实际 ${ach.count}`);
    if (!ach.unlocked) problems.push("成就列表没有任何已解锁项");
    if (!ach.hasBurgerKing) problems.push("成就列表缺少「汉堡王」");
    if (!ach.hasProgress) problems.push("成就列表缺少进度条");
    if (!ach.focusInside) problems.push("成就面板打开后焦点未进入");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);
    const achClosed = await page.evaluate(() => ({
      closed: !document.getElementById("ach-panel").classList.contains("show"),
      focusBack: document.activeElement && document.activeElement.id === "btn-ach",
    }));
    if (!achClosed.closed) problems.push("Esc 未关闭成就面板");
    if (!achClosed.focusBack) problems.push("成就面板关闭后焦点没有回到「成就」按钮");

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

    // 悬停：鼠标移到第一颗星，应出现餐品气泡。
    // 先 Esc 取消上一步的键盘选中 —— 卡片开着时，那颗星不再弹同名气泡（卡片第一行就是它）。
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
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

    // ---- 无障碍语义（浏览器里算出来的，不是读源码猜的）----
    // 静态标记由 tests/test_a11y_markup.py 兜底；这里只验"真的生效"的三件事：
    // 画布不是静态图语义、开关按钮的状态会变、导入报错能被读屏拿到。
    const sem = await page.evaluate(() => {
      const sky = document.getElementById("sky");
      const sound = document.getElementById("btn-sound");
      return {
        skyRole: sky.getAttribute("role"),
        skyDescribedBy: sky.getAttribute("aria-describedby"),
        hasMain: !!document.querySelector("main#main"),
        soundPressed: sound.getAttribute("aria-pressed"),
        toastRole: document.getElementById("toast").getAttribute("role"),
        errRole: document.getElementById("import-err").getAttribute("role"),
      };
    });
    if (sem.skyRole !== "application") problems.push(`画布 role 是 ${sem.skyRole}，读屏会把方向键吃掉`);
    if (!sem.skyDescribedBy) problems.push("画布没有 aria-describedby，键位说明无处可放");
    if (!sem.hasMain) problems.push("缺 main 地标");
    if (sem.toastRole !== "status") problems.push("#toast 不是 role=status，操作回执读屏听不到");
    if (sem.errRole !== "alert") problems.push("#import-err 不是 role=alert，导入报错读屏听不到");

    await page.click("#btn-more");
    await page.waitForTimeout(300);
    const moreOpen = await page.evaluate(() => document.getElementById("more-panel").classList.contains("show"));
    if (!moreOpen) problems.push("更多面板未打开");
    await page.click("#btn-sound");
    await page.waitForTimeout(250);
    const pressedAfter = await page.evaluate(() => document.getElementById("btn-sound").getAttribute("aria-pressed"));
    if (pressedAfter !== "true") problems.push(`音效开关点击后 aria-pressed=${pressedAfter}，读屏不知道现在是开还是关`);
    await page.click("#btn-sound");
    await page.waitForTimeout(150);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(150);
    const moreClosed = await page.evaluate(() => !document.getElementById("more-panel").classList.contains("show"));
    if (!moreClosed) problems.push("Esc 未关闭更多面板");

    // 导入错误路径：贴一段非法 JSON，输入框要被打上 aria-invalid
    await page.click("#import-open");
    await page.waitForTimeout(300);
    await page.fill("#import-text", "{not json");
    await page.click("#import-go");
    await page.waitForTimeout(300);
    const bad = await page.evaluate(() => ({
      invalid: document.getElementById("import-text").getAttribute("aria-invalid"),
      msg: document.getElementById("import-err").textContent || "",
      dialogName: (() => {
        const d = document.getElementById("import-panel");
        const id = d.getAttribute("aria-labelledby");
        const el = id ? document.getElementById(id) : null;
        return el ? (el.textContent || "").trim() : "";
      })(),
    }));
    if (bad.invalid !== "true") problems.push("非法 JSON 没有给输入框打 aria-invalid");
    if (!bad.msg) problems.push("非法 JSON 没有给出错误文案");
    if (!bad.dialogName) problems.push("导入面板的 aria-labelledby 指不到可见标题");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
    // 第四层浮层（导入面板）曾经漏掉 Esc 与焦点环，键盘用户按 Esc 没反应、Tab 还能跑到底下的画布
    const closed = await page.evaluate(() => !document.getElementById("import-panel").classList.contains("show"));
    if (!closed) problems.push("导入面板没有响应 Esc（另外三层都有，这层是后加的漏了）");

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
        // 图例是不是横排：看前两项是不是同一行（不看 display 值，网格/弹性都算横排）
        legendH: Math.round(lr.height),
        legendSameRow: (() => {
          const it = [...lg.children].map((e) => Math.round(e.getBoundingClientRect().top));
          return it.length > 1 && it[0] === it[1];
        })(),
        touchAction: getComputedStyle(document.getElementById("sky")).touchAction,
      };
    });
    if (!t.coarse) problems.push("触屏环境未识别为 coarse pointer（文案会退回鼠标版）");
    if (!/轻点|点按|捏合/.test(t.step2)) problems.push(`触屏引导文案没有触屏动作: ${t.step2}`);
    if (/悬停|滚轮|键盘/.test(t.step2)) problems.push(`触屏引导文案仍在讲鼠标/键盘: ${t.step2}`);
    if (!t.legendSameRow) problems.push("竖屏图例未改横排，会占掉纵向空间");
    if (t.legendH > 76) problems.push(`竖屏图例高度 ${t.legendH}px 超过两行预算`);
    if (t.touchAction !== "none") problems.push(`画布 touch-action=${t.touchAction}，双指手势会被浏览器截走`);

    // 星点不许钻进 HUD 底下：把整圈旋转角扫一遍，任何角度下星心落在 HUD 矩形内都算失败
    // （卡片不透明，钻进去=那颗星凭空消失）。这比截一张图可信，因为它覆盖所有角度。
    const hidden = await page.evaluate(() => {
      const ids = ["title", "hero", "persona", "actions", "stats"];
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
  if (opts.detailCheck) {
    // 引导层还没关的话，它是一整屏的遮罩，点哪儿都进不到画布 —— 先关掉再测落点
    await page.evaluate(() => {
      if (window.__mcuniverse.dismissOnboard) window.__mcuniverse.dismissOnboard();
    });
    await page.waitForTimeout(250);
    // 详情卡的落点体检：卡片是"贴着那颗星"弹出的，所以每一颗星都可能把它顶到别处。
    // 三件事不许发生：盖住刚点的那颗星（读详情时最需要它的位置）、压住可见 HUD、
    // 越出屏幕。旧实现是钉死的 left:50%/bottom:92px，360×640 上直接压住图例 ——
    // 这组断言就是为那类"定死一个坐标、换个屏就压"的老毛病准备的。
    const stars = await page.evaluate(() =>
      window.__mcuniverse.stars.map((s) => ({ x: Math.round(s.x), y: Math.round(s.y) })),
    );
    const bad = [];
    for (const st of stars) {
      await page.mouse.click(st.x, st.y);
      // 位置过渡 .3s：不等它落定量到的是动画中间帧（会误报）
      await page.waitForTimeout(420);
      const r = await page.evaluate(([sx, sy]) => {
        const d = document.getElementById("detail");
        const b = d.getBoundingClientRect();
        // footer 是贴右缘的竖排装饰字（低对比度责任声明），卡片靠右时允许压它 10 来像素，
        // 不列入硬断言；其余每一块都是用户要看/要点的东西。
        const HUD = ["title", "hero", "stats", "daily", "persona", "actions"];
        const hits = [];
        for (const id of HUD) {
          const el = document.getElementById(id);
          if (!el) continue;
          const cs = getComputedStyle(el);
          // opacity<.15 的是"让位中"的人格卡：它此刻是透明的，不算被压
          if (cs.display === "none" || parseFloat(cs.opacity) < 0.15) continue;
          const q = el.getBoundingClientRect();
          if (q.width < 2 || q.height < 2) continue;
          const ox = Math.min(b.right, q.right) - Math.max(b.left, q.left);
          const oy = Math.min(b.bottom, q.bottom) - Math.max(b.top, q.top);
          if (ox > 2 && oy > 2) hits.push(`${id} ${Math.round(ox)}×${Math.round(oy)}px`);
        }
        return {
          shown: d.classList.contains("show"),
          hits,
          covers: sx > b.left - 10 && sx < b.right + 10 && sy > b.top - 10 && sy < b.bottom + 10,
          outView: b.left < -1 || b.top < -1 || b.right > innerWidth + 1 || b.bottom > innerHeight + 1,
          rect: [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)],
        };
      }, [st.x, st.y]);
      if (!r.shown) bad.push(`点 (${st.x},${st.y}) 未弹出详情`);
      if (r.covers) bad.push(`(${st.x},${st.y}) 详情卡盖住了自己那颗星`);
      if (r.outView) bad.push(`(${st.x},${st.y}) 详情卡越界 ${r.rect.join("x")}`);
      if (r.hits.length) bad.push(`(${st.x},${st.y}) 详情卡压住 ${r.hits.join("、")}`);
    }
    // 收起之后人格卡必须回来（窄屏上它给抽屉让过位，不能让位就不还）
    await page.evaluate(() => document.getElementById("sky").focus());
    await page.keyboard.press("Escape");
    await page.waitForTimeout(320);
    const after = await page.evaluate(() => {
      const p = document.getElementById("persona");
      return {
        open: document.getElementById("detail").classList.contains("show"),
        yielded: p.classList.contains("yield"),
        opacity: parseFloat(getComputedStyle(p).opacity),
      };
    });
    if (after.open) bad.push("Esc 未收起详情卡");
    if (after.yielded || after.opacity < 0.5) bad.push("收起详情后人格卡没有回来");
    problems.push(...bad);
    state.detailAudit = `${stars.length} 颗星`;
  }
  if (opts.overlapCheck) {
    // HUD 互相压叠是这个项目反复复发的一类 bug（按钮被画布盖、徽章压副标、切换器重叠）。
    // 这里量真实布局矩形，任何两块可见 HUD 有 >2px 交集都算失败。
    const hits = await page.evaluate(() => {
      // detail / tip / toast 是按需弹出的浮层，允许盖住别的 HUD，不参与判定
      const ids = ["title", "hero", "stats", "daily", "persona", "actions"];
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
  if (opts.ui) {
    // 在线生成：打开面板 → 填示例 → 生成 → 断言星图被整体替换
    await page.click("#import-open");
    await page.waitForTimeout(400);
    const importOpen = await page.evaluate(() => document.getElementById("import-panel").classList.contains("show"));
    if (!importOpen) problems.push("粘贴订单面板未打开");
    await page.click("#import-sample");
    await page.waitForTimeout(200);
    await page.click("#import-go");
    await page.waitForTimeout(1500);
    const imported = await page.evaluate(() => ({
      stars: window.__mcuniverse.stars.length,
      persona: window.__mcuniverse.data.persona ? window.__mcuniverse.data.persona.name : null,
      badge: (document.getElementById("demo-badge").textContent || "").trim(),
      panel: document.getElementById("import-panel").classList.contains("show")
    }));
    if (imported.stars !== 3) problems.push(`导入后应有 3 颗星，实际 ${imported.stars}`);
    if (!imported.badge.includes("自定义")) problems.push(`导入后徽章未切换为自定义：${imported.badge}`);
    if (imported.panel) problems.push("导入后面板未关闭");
    state.imported = imported;
  }


  await page.close();
  return { url, state, problems };
}

/** ?open=import 深链：落地直接开面板，并且不能再排首访引导（两套模态会抢焦点）。 */
async function checkDeepLinkImport(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const problems = [];
  await page.goto(BASE + "?e2e=1&open=import", { waitUntil: "domcontentloaded", timeout: 90000 });
  const appeared = await page.waitForSelector("#import-panel.show", { timeout: 8000 })
    .then(() => true).catch(() => false);
  const state = await page.evaluate(() => {
    const mc = window.__mcuniverse;
    return {
      stars: mc ? mc.stars.length : -1,
      isNebula: mc ? mc.isNebula : null,
      persona: mc && mc.data.persona ? mc.data.persona.name : null,
      importOpen: mc ? mc.importOpen : false,
      onboardScheduled: mc ? mc.onboardScheduled : null,
    };
  });
  if (!appeared || !state.importOpen) problems.push("深链未打开粘贴订单面板");
  if (state.onboardScheduled !== false) problems.push("深链模式仍排了首访引导，会叠两层模态");
  await page.close();
  return { url: BASE + "?open=import", state, problems };
}

async function main() {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const results = [];
  results.push(await checkDeepLinkImport(browser));
  results.push(
    await checkPage(browser, BASE + "?e2e=1", {
      viewport: { width: 1280, height: 720 },
      expectNebula: false,
      expectStars: 10,
      exportCard: true,
      // 桌面档同时验两件事：引导等入场放完才弹（不能提前打断），六层浮层是真模态
      dialogs: true,
      onboardDeadline: 9000,
      onboardMin: 4000,
      ui: true,
      detailCheck: true,
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
      detailCheck: true,
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
      detailCheck: true,
    }),
  );
  const rm = await checkPage(browser, BASE + "?e2e=1&rm=1", {
    viewport: { width: 1280, height: 720 },
    expectNebula: false,
    expectStars: 10,
    reducedMotion: true,
    // 减少动效没有入场动画可等，引导不该再站 5.2 秒
    onboardDeadline: 2500,
  });
  if (rm.state.reduced !== true) rm.problems.push("prefers-reduced-motion 未生效");
  results.push(rm);
  // 分享卡交付：微信（安卓 X5 与 iOS WKWebView）内一律"预览 + 长按保存"，
  // 两种容器的提示文案不同（微信要多给一条"换浏览器打开"的兜底）
  results.push(
    await checkPage(browser, BASE + "?e2e=1&wx=1", {
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      ua: UA_WECHAT_ANDROID,
      delivery: "preview",
      wechatHint: true,
      expectNebula: false,
      expectStars: 10,
    }),
  );
  results.push(
    await checkPage(browser, BASE + "?e2e=1&ios=1", {
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      ua: UA_IOS_SAFARI,
      delivery: "preview",
      wechatHint: false,
      expectNebula: false,
      expectStars: 10,
    }),
  );
  // 同一台安卓设备的系统浏览器：这里必须还能下载（判据是容器，不是设备）
  results.push(
    await checkPage(browser, BASE + "?e2e=1&and=1", {
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      ua: UA_CHROME_ANDROID,
      delivery: "download",
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
      (r.state.cards ? ` cards=${Object.entries(r.state.cards).map(([k, v]) => k + ":" + Math.round(v / 1024) + "KB").join(" ")}` : ""));
    if (r.state.onboardAt) console.log(`     onboard=${r.state.onboardAt}ms`);
    if (r.state.saveMode) console.log(`     saveMode=${r.state.saveMode}`);
    if (r.state.download) console.log(`     download=${r.state.download}`);
    if (r.state.imported) console.log(`     import: ${r.state.imported.stars} 星 / ${r.state.imported.persona}`);
    if (r.state.pinch) console.log(`     pinch=${r.state.pinch}`);
    r.problems.forEach((p) => console.log("     - " + p));
  }
  process.exit(failed ? 1 : 0);
}

main().catch((e) => {
  console.error("E2E 运行失败:", e);
  process.exit(1);
});
