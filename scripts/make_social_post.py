"""拼 1080x1440 朋友圈配图：2x2 截图网格 + 标题条 + 底部地址条。

用法（仓库根目录）：
    "$PY" scripts/make_social_post.py
    "$PY" scripts/make_social_post.py --out <path.png>

默认输出到仓库同级的 输出/冲刺包/朋友圈配图/，可 --out 覆盖，可重复运行。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

SIZE = (1080, 1440)
BG_TOP = (13, 16, 38)
BG_BOTTOM = (30, 22, 56)
PANEL = (255, 255, 255, 20)
BORDER = (255, 255, 255, 46)
INK = (240, 242, 252)
INK_DIM = (186, 192, 224)

TITLE = "麦门宇宙 McUniverse"
SLOGAN = "把每一单麦当劳，变成一片只属于你的星空"
FOOT_URL = "http://47.114.38.125/mcd/demo/"
FOOT_NOTE = "打开即玩 · 无需登录"

ASSETS = ["submit-1.png", "submit-ach.png", "submit-3.png", "share-card-e2e.png"]

MARGIN = 28
GAP = 18
TITLE_H = 170
FOOT_H = 100


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["msyhbd.ttc", "msyh.ttc"] if bold else ["msyh.ttc", "msyhbd.ttc"]
    names += ["simhei.ttf", "simsun.ttc"]
    for name in names:
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def paint_bg(canvas: Image.Image) -> None:
    draw = ImageDraw.Draw(canvas)
    top, bottom = BG_TOP, BG_BOTTOM
    height = SIZE[1]
    for y in range(height):
        ratio = y / (height - 1)
        color = tuple(int(a + (b - a) * ratio) for a, b in zip(top, bottom, strict=False))
        draw.line([(0, y), (SIZE[0], y)], fill=color)


def rounded(image: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, image.size[0] - 1, image.size[1] - 1], radius=radius, fill=255)
    return mask


def paste_cell(canvas: Image.Image, shot: Image.Image, box: tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle(box, radius=20, fill=PANEL, outline=BORDER, width=2)
    inner_w, inner_h = box[2] - box[0] - 28, box[3] - box[1] - 28
    fitted = ImageOps.contain(shot, (inner_w, inner_h))
    fitted = fitted.convert("RGB")
    x = box[0] + (box[2] - box[0] - fitted.size[0]) // 2
    y = box[1] + (box[3] - box[1] - fitted.size[1]) // 2
    canvas.paste(fitted, (x, y), rounded(fitted, 14))


def build(assets_dir: Path, out_path: Path) -> Path:
    canvas = Image.new("RGB", SIZE, BG_TOP)
    paint_bg(canvas)
    draw = ImageDraw.Draw(canvas, "RGBA")

    draw.text((SIZE[0] // 2, 66), TITLE, font=load_font(62, bold=True), fill=INK, anchor="mm")
    draw.text((SIZE[0] // 2, 130), SLOGAN, font=load_font(30), fill=INK_DIM, anchor="mm")

    grid_h = SIZE[1] - TITLE_H - FOOT_H - MARGIN
    cell_w = (SIZE[0] - MARGIN * 2 - GAP) // 2
    cell_h = (grid_h - GAP) // 2
    for index, name in enumerate(ASSETS):
        col, row = index % 2, index // 2
        x0 = MARGIN + col * (cell_w + GAP)
        y0 = TITLE_H + row * (cell_h + GAP)
        shot = Image.open(assets_dir / name)
        paste_cell(canvas, shot, (x0, y0, x0 + cell_w, y0 + cell_h))

    draw.text((SIZE[0] // 2, SIZE[1] - 64), FOOT_URL, font=load_font(34, bold=True), fill=INK, anchor="mm")
    draw.text((SIZE[0] // 2, SIZE[1] - 26), FOOT_NOTE, font=load_font(22), fill=INK_DIM, anchor="mm")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG")
    return out_path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    default_out = repo_root.parents[0] / "冲刺包" / "朋友圈配图" / "mc-universe-1080x1440.png"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=repo_root / "docs" / "assets", help="截图素材目录")
    parser.add_argument("--out", type=Path, default=default_out, help="输出 PNG 路径")
    args = parser.parse_args()
    result = build(args.assets, args.out)
    print(f"written: {result} ({result.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
