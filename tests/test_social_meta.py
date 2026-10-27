"""社交预览元信息的守卫：CI 里没有微信，但"转发出去是张灰卡"是可以静态查出来的。

说明页曾经一份 og:meta 都没有 —— 它在投稿包里就是「作品简介链接」，评委转进群里
看到的是空白卡片。演示页有 og:image，但指向 submit-1.png（1.45MB），
抓取器普遍对缩略图有体积上限，大图经常直接不显示。

这里用临时目录造页面来验 check_meta：一半用例是**证伪**（故意写错，检查器必须报错），
否则"永远 PASS 的检查器"比没有检查器更危险。
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load():
    path = os.path.join(ROOT, "scripts", "check_meta.py")
    spec = importlib.util.spec_from_file_location("check_meta", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_meta"] = module
    spec.loader.exec_module(module)
    return module


check_meta = _load()
check = check_meta.check
SITE = check_meta.SITE

PAGE_OK = f"""<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="theme-color" content="#05040e">
<meta name="color-scheme" content="dark">
<link rel="icon" href="data:image/svg+xml,<svg/>">
<meta name="description" content="麦门宇宙">
<meta property="og:title" content="麦门宇宙">
<meta property="og:description" content="订单星图">
<meta property="og:type" content="website">
<meta property="og:image" content="{SITE}docs/assets/og-card.jpg">
<meta name="twitter:card" content="summary_large_image">
<title>麦门宇宙</title></head><body></body></html>"""


def build(tmp_path, html: str, og_bytes: int = 1024, og_name: str = "og-card.jpg"):
    """造一个最小站点：docs/about.html + docs/assets/<og_name>。"""
    docs = tmp_path / "docs"
    assets = docs / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (docs / "about.html").write_text(html, encoding="utf-8")
    (assets / og_name).write_bytes(b"\xff" * og_bytes)
    return str(tmp_path)


def test_ok_page_passes(tmp_path):
    root = build(tmp_path, PAGE_OK)
    assert check(root) == []


def test_missing_og_image_is_reported(tmp_path):
    """证伪：删掉 og:image，检查器必须报缺字段（说明页当初就是这个状态）。"""
    html = PAGE_OK.replace(f'<meta property="og:image" content="{SITE}docs/assets/og-card.jpg">', "")
    problems = check(build(tmp_path, html))
    assert any("og:image" in why for _, why in problems), problems


def test_oversized_thumbnail_is_reported(tmp_path):
    """证伪：缩略图 1.45MB（就是当年那张 submit-1.png 的体积），必须报超重。"""
    problems = check(build(tmp_path, PAGE_OK, og_bytes=1_450_000))
    assert any("KB" in why and "超过" in why for _, why in problems), problems


def test_png_thumbnail_is_reported(tmp_path):
    """证伪：换成 PNG 也要报 —— 这个位置的 PNG 动辄上兆。"""
    html = PAGE_OK.replace("og-card.jpg", "og-card.png")
    problems = check(build(tmp_path, html, og_name="og-card.png"))
    assert any("JPG/WebP" in why for _, why in problems), problems


def test_relative_or_foreign_og_image_is_reported(tmp_path):
    """证伪：相对路径 / 外站地址，抓取器都不认，必须报。"""
    for bad in ("docs/assets/og-card.jpg", "https://example.com/a.jpg"):
        html = PAGE_OK.replace(f"{SITE}docs/assets/og-card.jpg", bad)
        problems = check(build(tmp_path, html))
        assert any("og:image" in why for _, why in problems), (bad, problems)


def test_missing_favicon_is_reported(tmp_path):
    html = PAGE_OK.replace('<link rel="icon" href="data:image/svg+xml,<svg/>">', "")
    problems = check(build(tmp_path, html))
    assert any("favicon" in why for _, why in problems), problems


def test_meta_attribute_order_does_not_matter(tmp_path):
    """content 写在 name 前面的写法（手写时常这样）不能被判成"缺字段"。"""
    html = PAGE_OK.replace(
        '<meta property="og:title" content="麦门宇宙">',
        '<meta content="麦门宇宙" property="og:title">',
    )
    assert check(build(tmp_path, html)) == []


@pytest.mark.parametrize("rel", ["demo/index.html", "docs/about.html"])
def test_real_pages_pass(rel):
    """实际仓库里的页面必须过 —— 这条会在 CI 里跑。"""
    assert os.path.isfile(os.path.join(check_meta.ROOT, rel))
    problems = [p for p in check() if p[0] == rel]
    assert problems == [], problems
