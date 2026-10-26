/**
 * README 演示动图生成器：录一段真实入场动画 → 转成轻量 GIF。
 *
 * README 的第一眼就是这张图，所以它必须和当前界面同步（文案、构图、星点大小）。
 * 以前是手工录 + 手工转码，界面一改就过期；这里固定成一条命令。
 *
 * 用法：
 *   FFMPEG=<ffmpeg 路径> node scripts/make_gif.mjs [baseUrl] [out.gif]
 *   ffmpeg 缺失时可用：pip install imageio-ffmpeg
 *     python -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const BASE = process.argv[2] || "http://127.0.0.1:8123/demo/";
const OUT = process.argv[3] || "docs/assets/demo.gif";
const FFMPEG = process.env.FFMPEG;
if (!FFMPEG) {
  console.error("缺少 FFMPEG 环境变量。可用 imageio-ffmpeg 自带的二进制：");
  console.error('  python -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"');
  process.exit(1);
}

const W = 1280;
const H = 800;

async function record() {
  const dir = mkdtempSync(join(tmpdir(), "mc-gif-"));
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const ctx = await browser.newContext({
    viewport: { width: W, height: H },
    recordVideo: { dir, size: { width: W, height: H } },
  });
  const page = await ctx.newPage();
  await page.goto(BASE + "?gif=1", { waitUntil: "domcontentloaded" });
  // 首访引导 5.2s 才弹，必须提前关掉：录屏里它会在星图成形的那一刻挡住整屏
  await page.evaluate(() => {
    if (window.__mcuniverse && window.__mcuniverse.dismissOnboard) window.__mcuniverse.dismissOnboard();
  });
  // 入场：粒子汇聚成字（2.6s）→ 定格 1s → 炸开成星图
  await page.waitForTimeout(5400);
  // 首访引导在 5.2s 弹出，录屏里必须关掉，否则整段动图被遮罩压住
  await page.evaluate(() => {
    if (window.__mcuniverse && window.__mcuniverse.dismissOnboard) window.__mcuniverse.dismissOnboard();
  });
  await page.waitForTimeout(900);
  // 悬停一颗星，展示气泡
  const target = await page.evaluate(() => {
    const stars = window.__mcuniverse.stars;
    let best = null, bestD = -1;
    for (const s of stars) {
      let d = Infinity;
      for (const o of stars) if (o !== s) d = Math.min(d, Math.hypot(o.x - s.x, o.y - s.y));
      if (d > bestD) { bestD = d; best = s; }
    }
    return best ? { x: Math.round(best.x), y: Math.round(best.y) } : null;
  });
  if (target) {
    await page.mouse.move(target.x, target.y, { steps: 12 });
    await page.waitForTimeout(2600);
  }
  const video = page.video();
  await ctx.close();
  await browser.close();
  const file = readdirSync(dir).find((f) => f.endsWith(".webm"));
  if (!file) throw new Error("没有录到视频");
  return join(dir, file);
}

function encode(input) {
  const palette = join(tmpdir(), "mc-palette.png");
  // 600px / 8fps / 48 色 / 10.2s ≈ 2.0MB：兼顾清晰度与 GitHub 首屏加载
  const vf = "fps=10,scale=600:-1:flags=lanczos";
  execFileSync(FFMPEG, ["-y", "-i", input, "-vf", `${vf},palettegen=max_colors=48`, palette], {
    stdio: "ignore",
  });
  execFileSync(
    FFMPEG,
    [
      "-y", "-t", "10.2", "-i", input, "-i", palette,
      "-lavfi", `${vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5`,
      "-loop", "0", OUT,
    ],
    { stdio: "ignore" },
  );
}

const webm = await record();
encode(webm);
writeFileSync("/tmp/mc-gif-source.txt", webm);
console.log(`GIF 已生成: ${OUT}`);
