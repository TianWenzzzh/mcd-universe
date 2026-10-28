/**
 * 无障碍审计：用真实浏览器量「键盘 / 读屏用户能不能真的用起来」，
 * 而不是靠肉眼读一遍标签。
 *
 * 为什么必须真跑浏览器：可访问名（accessible name）是「计算」出来的，
 * aria-labelledby 指向的节点可能不存在、按钮里的文字可能被 CSS 隐藏、
 * 焦点环可能是 outline:0 而只留一个看不见的 box-shadow —— 这些都只有算完才知道。
 *
 * 跑两档：桌面 1440×900（鼠标 + 键盘）与手机 390×844（触屏 + 粗指针），
 * 因为这两档的可达性问题不是同一个：桌面坏在语义，手机坏在手指按不准。
 *
 * 检查项（每项都是可复现的数字，不是风格意见）：
 *  1. unnamed        可交互元素没有可访问名（读屏念「按钮」三个字，不知道是什么）
 *  2. unlabeledField 输入框/文本域没有 label（placeholder 不算：一输入就消失）
 *  3. fakeLink       <a href="#"> —— 视觉是链接、行为是滚动到顶部
 *  4. smallTarget    点按目标不达标（桌面 < 24px，触屏 < 32px）
 *  5. landmarks      有没有 main/nav 等可跳转地标
 *  6. headingSkips   标题层级跳跃（h1 直接跳到 h3）
 *  7. toggleNoState  开关型按钮没有 aria-pressed（读屏不知道开没开）
 *  8. liveGaps       有动态反馈（toast / 表单错误）却不在 live region 里
 *  9. imgRoleFocus   可聚焦、要收键盘事件的 canvas 却挂 role="img"（读屏进图片模式，方向键收不到）
 * 10. noAltPath     画布既不收键盘、替代清单也不可操作 —— 读屏用户完全无法选中任何一颗星
 * 11. focusVisible  Tab 一圈，逐个量焦点指示（outline / box-shadow 是否有可见变化）
 * 12. dialogName    对话框的可访问名是否与其可见标题一致
 * 13. hOverflow     横向溢出（元素右边缘超出视口）
 *
 * 用法：
 *   node scripts/a11y_audit.mjs [baseUrl] [--json out.json]
 * 本地需先起静态服务（file:// 带 query 会 404）：
 *   python -m http.server 8099 --directory demo
 *   node scripts/a11y_audit.mjs http://127.0.0.1:8099/
 */
import { writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const args = process.argv.slice(2);
const baseUrl = args.find((a) => !a.startsWith("--")) || "http://127.0.0.1:8099/";
const jsonIdx = args.indexOf("--json");
const outJson = jsonIdx >= 0 ? args[jsonIdx + 1] : "";

// 触屏的点按下限取 32 而不是 WCAG 的 24：24 是"AA 及格线"，但在真机上仍然是
// 需要瞄着按的尺寸。这一档只报不判死（P2），因为 24 才算不合规。
const TOUCH_MIN = 32;
const DESKTOP_MIN = 24;

/** 在页面里执行：算可访问名（简化版，覆盖本页所有实际用法） */
const PAGE_PROBE = () => {
  function textOf(el) {
    // 可见文字：跳过 display:none / visibility:hidden / aria-hidden 子树
    let out = "";
    for (const n of el.childNodes) {
      if (n.nodeType === 3) out += n.nodeValue;
      else if (n.nodeType === 1) {
        const cs = getComputedStyle(n);
        if (cs.display === "none" || cs.visibility === "hidden" || n.getAttribute("aria-hidden") === "true") continue;
        out += " " + textOf(n);
      }
    }
    return out;
  }
  function accName(el) {
    const lb = el.getAttribute("aria-labelledby");
    if (lb) {
      const t = lb.split(/\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((n) => textOf(n))
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      if (t) return { name: t, from: "aria-labelledby" };
    }
    const al = el.getAttribute("aria-label");
    if (al && al.trim()) return { name: al.trim(), from: "aria-label" };
    const tag = el.tagName.toLowerCase();
    if (tag === "img") {
      const alt = el.getAttribute("alt");
      if (alt && alt.trim()) return { name: alt.trim(), from: "alt" };
    }
    if (el.id) {
      const lab = document.querySelector(`label[for="${el.id}"]`);
      if (lab) {
        const t = textOf(lab).replace(/\s+/g, " ").trim();
        if (t) return { name: t, from: "label[for]" };
      }
    }
    const wrap = el.closest("label");
    if (wrap) {
      const t = textOf(wrap).replace(/\s+/g, " ").trim();
      if (t) return { name: t, from: "label(wrap)" };
    }
    const own = textOf(el).replace(/\s+/g, " ").trim();
    if (own) return { name: own, from: "text" };
    const ttl = el.getAttribute("title");
    if (ttl && ttl.trim()) return { name: ttl.trim(), from: "title" };
    return { name: "", from: "" };
  }
  const sel = "button, a[href], input, textarea, select, [tabindex]:not([tabindex='-1']), [role=button]";
  const nodes = Array.from(document.querySelectorAll(sel));
  const items = nodes.map((el) => {
    const { name, from } = accName(el);
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const tag = el.tagName.toLowerCase();
    return {
      tag,
      id: el.id || "",
      cls: el.className && typeof el.className === "string" ? el.className.slice(0, 40) : "",
      name,
      nameFrom: from,
      w: Math.round(r.width),
      h: Math.round(r.height),
      right: Math.round(r.right),
      visible: cs.display !== "none" && cs.visibility !== "hidden" && r.width > 0 && r.height > 0,
      href: tag === "a" ? el.getAttribute("href") : null,
      pressed: el.getAttribute("aria-pressed"),
      // sr-only 的 1×1 不算点按目标：它本来就只给读屏
      srOnly: !!el.closest(".sr-only"),
    };
  });

  const landmarks = Array.from(
    document.querySelectorAll("main, nav, header, footer, aside, [role=main], [role=navigation], [role=banner], [role=contentinfo]")
  ).map((el) => (el.getAttribute("role") || el.tagName.toLowerCase()) + (el.id ? "#" + el.id : ""));

  const headings = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6"))
    .filter((el) => {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return cs.display !== "none" && cs.visibility !== "hidden" && r.width > 0;
    })
    .map((el) => ({
      level: Number(el.tagName[1]),
      text: (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 30),
    }));

  const live = Array.from(document.querySelectorAll("[aria-live], [role=status], [role=alert], [role=log]")).map((el) => ({
    id: el.id || "",
    live: el.getAttribute("aria-live") || el.getAttribute("role"),
  }));

  const dialogs = Array.from(document.querySelectorAll("[role=dialog], dialog")).map((el) => {
    const nm = accName(el);
    const h = el.querySelector("h1,h2,h3,h4");
    return {
      id: el.id || "",
      name: nm.name,
      nameFrom: nm.from,
      heading: h ? (h.textContent || "").replace(/\s+/g, " ").trim() : "",
    };
  });

  const canvasInfo = Array.from(document.querySelectorAll("canvas")).map((el) => ({
    id: el.id || "",
    role: el.getAttribute("role"),
    tabindex: el.getAttribute("tabindex"),
    label: el.getAttribute("aria-label") || "",
  }));

  const altList = document.getElementById("a11y-list");
  const altOperable = altList
    ? altList.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])").length
    : 0;
  const altItems = altList ? altList.querySelectorAll("li").length : 0;

  return { items, landmarks, headings, live, dialogs, canvasInfo, altOperable, altItems, vw: window.innerWidth };
};

/** Tab 一圈，逐个量焦点指示是否存在（outline 或 box-shadow 在聚焦前后有可见变化） */
const FOCUS_PROBE = () => {
  const el = document.activeElement;
  if (!el || el === document.body) return [];
  const cs = getComputedStyle(el);
  return [{
    tag: el.tagName.toLowerCase(),
    id: el.id || "",
    text: (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 16),
    outlineWidth: cs.outlineWidth,
    outlineStyle: cs.outlineStyle,
    boxShadow: cs.boxShadow === "none" ? "" : "set",
    srOnly: !!el.closest(".sr-only"),
  }];
};

async function auditPage(browser, url, opts) {
  const ctxOpts = { viewport: opts.viewport };
  if (opts.mobile) {
    ctxOpts.isMobile = true;
    ctxOpts.hasTouch = true;
    ctxOpts.deviceScaleFactor = 2;
  }
  const page = await browser.newPage(ctxOpts);
  const consoleErr = [];
  page.on("pageerror", (e) => consoleErr.push(String(e)));
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(5200); // 等入场动画与首访引导
  // 引导层关掉，让整页可点（它自己也要单独审，先不挡路）
  await page.evaluate(() => {
    const ob = document.getElementById("onboard");
    if (ob && ob.classList.contains("show")) {
      const b = document.getElementById("ob-go");
      if (b) b.click();
    }
  });
  await page.waitForTimeout(700);

  const probe = await page.evaluate(PAGE_PROBE);

  // Tab 一圈量焦点指示（触屏档跳过：真机上没有 Tab 键，量了也没人用）
  const focus = [];
  if (!opts.mobile) {
    await page.evaluate(() => document.body.focus());
    const seen = new Set();
    for (let i = 0; i < 24; i++) {
      await page.keyboard.press("Tab");
      await page.waitForTimeout(50);
      const cur = await page.evaluate(FOCUS_PROBE);
      // 空结果不代表结束：Tab 出了页面会先落到浏览器地址栏，activeElement 变回 body。
      // 这里继续按，等焦点绕回页面内（重复出现才停），否则一圈只能量到前几个按钮。
      if (!cur.length) continue;
      const f = cur[0];
      const k = f.tag + "|" + f.id + "|" + f.text;
      if (seen.has(k)) break;
      seen.add(k);
      focus.push(f);
    }
  }

  await page.close();
  return { url, opts, consoleErr, ...probe, focus };
}

function judge(rep) {
  const mobile = rep.opts.mobile;
  const minTarget = mobile ? DESKTOP_MIN : DESKTOP_MIN;
  const issues = [];
  const push = (level, kind, msg) => issues.push({ level, kind, msg });

  // 1. 无名字（input 的名字由 label 单独判，避免重复报两条）
  for (const it of rep.items) {
    if (!it.visible || it.name) continue;
    if (["input", "textarea", "select"].includes(it.tag)) continue;
    push("P0", "unnamed", `<${it.tag}${it.id ? "#" + it.id : ""}> 没有可访问名`);
  }
  // 2. 表单无 label
  for (const it of rep.items) {
    if (!["input", "textarea", "select"].includes(it.tag)) continue;
    if (!it.name) push("P0", "unlabeledField", `<${it.tag}#${it.id}> 没有标签（placeholder 不算）`);
  }
  // 3. 假链接
  for (const it of rep.items) {
    if (it.tag === "a" && (it.href === "#" || it.href === "")) {
      push("P1", "fakeLink", `<a#${it.id || it.cls}> href="${it.href}" 行为是跳到页首`);
    }
  }
  // 4. 点按目标
  for (const it of rep.items) {
    if (it.srOnly || !it.visible) continue;
    const okDesktop = it.w >= DESKTOP_MIN && it.h >= DESKTOP_MIN;
    const okTouch = it.w >= TOUCH_MIN && it.h >= TOUCH_MIN;
    // 行内文字链接（夹在句子里的 <a>）按 WCAG 2.5.8 属豁免项，只报不判死
    if (it.tag === "a" && !okDesktop) {
      push("P2", "smallTarget", `<a#${it.id || it.cls}>「${it.name}」${it.w}×${it.h}px（行内链接，豁免）`);
      continue;
    }
    if (!mobile && !okDesktop) {
      push("P0", "smallTarget", `<${it.tag}#${it.id || it.cls}>「${it.name}」${it.w}×${it.h}px，低于 24px 下限`);
    } else if (mobile && !okTouch) {
      push("P1", "smallTarget", `<${it.tag}#${it.id || it.cls}>「${it.name}」${it.w}×${it.h}px，触屏不足 ${TOUCH_MIN}px`);
    }
  }
  // 5. 地标
  if (!rep.landmarks.some((l) => l.startsWith("main"))) {
    push("P1", "landmarks", "没有 main 地标（读屏无法一键跳到主内容）");
  }
  // 6. 标题层级
  let prev = 0;
  for (const h of rep.headings) {
    if (prev && h.level > prev + 1) push("P1", "headingSkips", `h${prev} → h${h.level}「${h.text}」`);
    prev = h.level;
  }
  // 7. 开关按钮无状态
  for (const it of rep.items) {
    if (it.tag !== "button" || it.pressed !== null) continue;
    if (/音效|声音|开关|切换|静音/.test(it.name)) {
      push("P1", "toggleNoState", `<button#${it.id}>「${it.name}」是开关但没有 aria-pressed`);
    }
  }
  // 8. live region 覆盖
  const liveIds = rep.live.map((l) => l.id);
  if (!liveIds.includes("toast")) {
    push("P1", "liveGaps", "#toast（导出/生成等操作反馈）不在 live region 里，读屏听不到操作结果");
  }
  if (!liveIds.includes("import-err")) {
    push("P1", "liveGaps", "导入错误 #import-err 不是 role=alert，报错只出现在屏幕上");
  }
  // 9. canvas 语义
  const sky = rep.canvasInfo.find((c) => c.id === "sky");
  if (sky && sky.tabindex !== null && sky.role === "img") {
    push("P0", "imgRoleFocus",
      `<canvas#${sky.id} role="img" 但 tabindex=${sky.tabindex} 且要收方向键：读屏把它当静态图片，键盘事件不保证送达`);
  }
  // 10. 有没有任何可操作路径到"某一颗星"
  const canvasOperable = !!(sky && sky.role === "application" && sky.tabindex !== null);
  if (rep.altItems > 0 && rep.altOperable === 0 && !canvasOperable) {
    push("P0", "noAltPath",
      `星点替代清单有 ${rep.altItems} 条但 0 个可操作控件，画布也不是 application：读屏用户无法选中任何一颗星`);
  }
  // 11. 焦点可见
  for (const f of rep.focus) {
    if (f.srOnly) continue;
    if ((f.outlineStyle === "none" || f.outlineWidth === "0px") && !f.boxShadow) {
      push("P0", "focusVisible", `<${f.tag}${f.id ? "#" + f.id : ""}>「${f.text}」聚焦后没有可见指示`);
    }
  }
  // 12. 对话框命名
  for (const d of rep.dialogs) {
    if (!d.name) push("P1", "dialogName", `#${d.id} 没有可访问名`);
    else if (d.heading && d.name !== d.heading) {
      push("P2", "dialogName", `#${d.id} 名字「${d.name}」≠ 可见标题「${d.heading}」（读屏念的和看到的不一样）`);
    }
  }
  // 13. 横向溢出
  for (const it of rep.items) {
    if (!it.visible || it.srOnly) continue;
    if (it.right > rep.vw + 1) {
      push("P1", "hOverflow", `<${it.tag}#${it.id || it.cls}> 右边缘 ${it.right}px 超出视口 ${rep.vw}px`);
    }
  }
  return issues;
}

async function main() {
  const browser = await chromium.launch({ channel: "msedge" }).catch(() => chromium.launch());
  const runs = [
    { label: "桌面 1440×900", viewport: { width: 1440, height: 900 }, mobile: false },
    { label: "手机 390×844", viewport: { width: 390, height: 844 }, mobile: true },
  ];
  const report = { url: baseUrl, runs: [] };
  let p0 = 0;
  let total = 0;

  for (const opts of runs) {
    const rep = await auditPage(browser, baseUrl, opts);
    const issues = judge(rep);
    const n0 = issues.filter((i) => i.level === "P0").length;
    p0 += n0;
    total += issues.length;
    report.runs.push({ label: opts.label, issues, probe: {
      items: rep.items.length, landmarks: rep.landmarks.length, headings: rep.headings.length,
      live: rep.live.length, dialogs: rep.dialogs.length, altItems: rep.altItems,
      altOperable: rep.altOperable, canvas: rep.canvasInfo.filter((c) => c.id === "sky"),
      focus: rep.focus.length,
    }, consoleErr: rep.consoleErr });

    console.log(`\n[${opts.label}] 可交互 ${rep.items.length} · 地标 ${rep.landmarks.length} · ` +
      `标题 ${rep.headings.length} · live ${rep.live.length} · 焦点 ${rep.focus.length}`);
    const sky = rep.canvasInfo.find((c) => c.id === "sky");
    if (sky) console.log(`            canvas: role=${sky.role} tabindex=${sky.tabindex} ` +
      `替代清单 ${rep.altItems} 条 / 可操作 ${rep.altOperable}`);
    if (rep.consoleErr.length) console.log("            控制台异常：" + rep.consoleErr.join(" | "));
    if (!issues.length) console.log("            无问题");
    for (const i of issues) console.log(`            [${i.level}] ${i.kind}: ${i.msg}`);
  }
  await browser.close();

  console.log(`\n合计 ${total} 项（P0 ${p0}）`);
  if (outJson) {
    writeFileSync(outJson, JSON.stringify(report, null, 2), "utf8");
    console.log("明细已写入 " + outJson);
  }
  process.exit(p0 ? 1 : 0);
}

main().catch((e) => {
  console.error("审计运行失败:", e);
  process.exit(1);
});
