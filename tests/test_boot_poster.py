"""首屏关键帧：封面必须轻量，且四个演示页内嵌的是同一份真实星图。"""

from __future__ import annotations

import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTER = ROOT / "docs" / "assets" / "boot-poster.jpg"
PAGES = ["index.html", "breakfast.html", "dessert.html", "burger.html"]
BOOT_RE = re.compile(r'id="boot-cover"[^>]*><img src="data:image/jpeg;base64,([^"]+)"')


def test_boot_poster_is_small_jpeg() -> None:
    data = POSTER.read_bytes()
    assert data.startswith(b"\xff\xd8"), "首屏封面必须是 JPEG"
    assert len(data) <= 30 * 1024, f"首屏封面 {len(data) / 1024:.1f}KB 超过 30KB 预算"


def test_demo_pages_embed_current_poster() -> None:
    expected = POSTER.read_bytes()
    for name in PAGES:
        html = (ROOT / "demo" / name).read_text(encoding="utf-8")
        assert "__BOOT_POSTER__" not in html, f"{name} 仍有未替换的封面占位符"
        match = BOOT_RE.search(html)
        assert match, f"{name} 缺少内联首屏封面"
        assert base64.b64decode(match.group(1)) == expected, f"{name} 内嵌封面与当前资产不一致"
