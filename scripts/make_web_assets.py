"""把投稿用的大图压成网页版：PNG 2x 截图 -> 渐进式 JPEG。

原图只用于投稿上传；镜像与页面必须用 *-web.jpg，否则 1.3Mbps 出口会把
说明页拖到十几秒。这个脚本让"重拍截图后同步网页版"不再靠手敲 Pillow。

用法：
    python scripts/make_web_assets.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"

# 源文件 -> (网页版最大宽度, JPEG 质量)
JOBS = {
    "submit-1.png": (1600, 82),
    "submit-2.png": (1600, 82),
    "submit-3.png": (1600, 82),
    "demo-detail.png": (1200, 84),
    "share-card-minimal.png": (1080, 86),
}


def convert(name: str, max_width: int, quality: int) -> None:
    src = ASSETS / name
    if not src.is_file():
        print(f"skip {name}（不存在）")
        return
    im = Image.open(src).convert("RGB")
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
    out = ASSETS / f"{src.stem}-web.jpg"
    im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    print(f"{name}: {src.stat().st_size / 1e6:.2f}MB -> {out.name} {out.stat().st_size / 1e6:.2f}MB")


def main() -> None:
    for name, (width, quality) in JOBS.items():
        convert(name, width, quality)


if __name__ == "__main__":
    main()
