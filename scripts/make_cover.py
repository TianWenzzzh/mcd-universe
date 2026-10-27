"""生成参赛作品墙封面（1200x630）与同款社交预览图。

素材只用当前产品的真实 Canvas 星图（cover-source.jpg），文案只写已实现能力：
7 种人格、4 款分享卡、在线生成。所有文字在 300px 宽缩略图下仍保留层级。

用法：
    python scripts/make_cover.py
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
POSTER = ROOT / "docs" / "assets" / "cover-source.jpg"
COVER = ROOT / "docs" / "assets" / "contest-cover.jpg"
OG = ROOT / "docs" / "assets" / "og-card.jpg"

W, H = 1200, 630
S = 2  # 先画 2 倍再缩小，中文小字不糊
BG = (4, 3, 11)
GOLD = (255, 233, 168)
WHITE = (242, 238, 252)
MUTED = (185, 179, 214)


def _font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = [os.path.join(windir, "Fonts", name) for name in names]
    candidates += [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    raise SystemExit("找不到中文字体，请安装微软雅黑 / 思源黑体后重试")


def _cover_background() -> Image.Image:
    src = Image.open(POSTER).convert("RGB")
    scale = max((W * S) / src.width, (H * S) / src.height)
    resized = src.resize((round(src.width * scale), round(src.height * scale)), Image.LANCZOS)
    left = (resized.width - W * S) // 2
    top = (resized.height - H * S) // 2
    bg = resized.crop((left, top, left + W * S, top + H * S)).convert("RGBA")

    # 左侧压暗到接近实色，右侧保留星图。用逐列渐变而不是整块蒙版，
    # 标题区对比度足够，右侧星点又不会被压灰。
    shade = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    px = shade.load()
    edge = int(W * S * 0.72)
    for x in range(edge):
        alpha = int(246 * (1 - x / edge) ** 1.25)
        for y in range(H * S):
            px[x, y] = (*BG, alpha)
    bg.alpha_composite(shade)

    veil = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(veil)
    d.rectangle([0, int(H * S * 0.78), W * S, H * S], fill=(0, 0, 0, 70))
    bg.alpha_composite(veil)
    return bg


def _pill(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.FreeTypeFont) -> None:
    pad_x, pad_y = 18 * S, 10 * S
    box = draw.textbbox((0, 0), text, font=font)
    bw, bh = box[2] - box[0], box[3] - box[1]
    w, h = bw + pad_x * 2, bh + pad_y * 2
    draw.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=h // 2,
        fill=(25, 21, 43),
        outline=(171, 146, 82),
        width=max(1, S),
    )
    draw.text((x + pad_x, y + pad_y - box[1]), text, font=font, fill=GOLD)


def build() -> None:
    img = _cover_background()
    f_bold = _font(["msyhbd.ttc", "simhei.ttf"], 24 * S)
    f_title = _font(["msyhbd.ttc", "simhei.ttf"], 136 * S)
    f_sub = _font(["msyh.ttc", "simhei.ttf"], 46 * S)
    f_meta = _font(["msyh.ttc", "simhei.ttf"], 26 * S)
    f_cta = _font(["msyhbd.ttc", "simhei.ttf"], 26 * S)

    x = 64 * S
    d = ImageDraw.Draw(img)
    d.text((x, 44 * S), "MCUNIVERSE  ·  订单星图", font=f_bold, fill=(163, 157, 194))

    # 真发光要单独一层做高斯模糊，再合成；直接在 RGBA 上画半透明字会被转 RGB 时抹平。
    glow = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).text((x, 92 * S), "麦门宇宙", font=f_title, fill=(*GOLD, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(9 * S))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    d.text((x, 92 * S), "麦门宇宙", font=f_title, fill=GOLD)

    d.multiline_text(
        (x, 276 * S),
        "把每一单麦当劳，\n点亮成你的专属星海。",
        font=f_sub,
        fill=WHITE,
        spacing=12 * S,
    )
    d.text((x, 432 * S), "订单星图  ·  7 种麦门人格  ·  4 款分享卡", font=f_meta, fill=MUTED)

    _pill(d, x, 478 * S, "打开即玩  ·  无需登录", f_cta)

    # 右侧保留一条极淡的金线，给星图一个视觉落点，不遮挡星点
    d.line([(W * S - 54 * S, 44 * S), (W * S - 54 * S, H * S - 44 * S)], fill=(74, 63, 42), width=S)

    out = img.convert("RGB").resize((W, H), Image.LANCZOS)
    out.save(COVER, "JPEG", quality=88, optimize=True, progressive=True)
    out.save(OG, "JPEG", quality=88, optimize=True, progressive=True)
    print(f"cover: {COVER.relative_to(ROOT)} ({COVER.stat().st_size / 1024:.0f}KB)")
    print(f"og:    {OG.relative_to(ROOT)} ({OG.stat().st_size / 1024:.0f}KB)")


if __name__ == "__main__":
    build()
