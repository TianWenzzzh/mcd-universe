"""社交卡片抓取的判定逻辑：CI 里没有公网也没有微信，但"卡片会不会是灰的"可以静态判定。

这一层两件事值得守：
  1. 页面声明的图必须和页面同主机 —— 镜像页曾经声明 github.io（图在镜像上本来就有），
     抓取器为了取一张 72KB 的图要多跨一站，那台主机在国内时好时坏；
  2. 声明尺寸必须等于真实像素 —— 声明 1200×630、实际 1080×1440 时，卡片会被裁成一条。

判定函数全是纯函数（html 进、问题出；字节进、指标出），所以这里不发一个请求也能测。
每条主断言都配一条**证伪**：故意写坏，判定必须报错。
"""

from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


social = _load("check_social", "scripts/check_social.py")

PAGE_OK = """<!DOCTYPE html><html lang="zh-CN"><head>
<meta property="og:title" content="麦门宇宙 McUniverse">
<meta property="og:description" content="你的每一单，都是麦门宇宙里的一颗星。">
<meta property="og:image" content="https://tianwenzzzh.github.io/mcd-universe/docs/assets/og-card.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:type" content="website">
<meta property="og:url" content="https://tianwenzzzh.github.io/mcd-universe/demo/">
<meta property="og:site_name" content="麦门宇宙 McUniverse">
</head><body></body></html>"""

PAGE_URL = "https://tianwenzzzh.github.io/mcd-universe/demo/"


def fake_jpeg(w: int, h: int, pad: int = 0) -> bytes:
    """造一个只有文件头的最小 JPEG（SOF0 段里带真实像素尺寸）。"""
    sof = (
        b"\xff\xc0"
        + (17).to_bytes(2, "big")
        + b"\x08"
        + h.to_bytes(2, "big")
        + w.to_bytes(2, "big")
        + b"\x03"
        + b"\x01\x11\x00" * 3
        + b"\x00" * pad
    )
    return b"\xff\xd8" + sof + b"\xff\xd9"


def test_page_ok() -> None:
    assert social.audit_page(PAGE_OK, PAGE_URL) == []


def test_cross_host_image_is_reported() -> None:
    """证伪：镜像页声明 github.io 的图（本轮修掉的那个真实状态）必须被判出来。"""
    problems = social.audit_page(PAGE_OK, "http://47.114.38.125/mcd/demo/")
    assert any("og:image 跨主机" in p for p in problems), problems


def test_cross_host_og_url_is_reported() -> None:
    """证伪：链接点在镜像、og:url 说自己是 Pages，同样要报。"""
    html = PAGE_OK.replace(
        '<meta property="og:url" content="https://tianwenzzzh.github.io/mcd-universe/demo/">',
        '<meta property="og:url" content="http://47.114.38.125/mcd/demo/">',
    )
    problems = social.audit_page(html, PAGE_URL)
    assert any("og:url 跨主机" in p for p in problems), problems


def test_missing_og_url_is_reported() -> None:
    """证伪：四个演示页此前都没有 og:url。"""
    html = PAGE_OK.replace('<meta property="og:url" content="https://tianwenzzzh.github.io/mcd-universe/demo/">', "")
    problems = social.audit_page(html, PAGE_URL)
    assert any("og:url" in p for p in problems), problems


def test_relative_image_is_reported() -> None:
    html = PAGE_OK.replace(
        "https://tianwenzzzh.github.io/mcd-universe/docs/assets/og-card.jpg", "docs/assets/og-card.jpg"
    )
    problems = social.audit_page(html, PAGE_URL)
    assert any("相对地址" in p for p in problems), problems


def test_long_title_is_reported() -> None:
    html = PAGE_OK.replace("麦门宇宙 McUniverse", "麦" * (social.TITLE_MAX + 1))
    assert any("og:title" in p and "超过" in p for p in social.audit_page(html, PAGE_URL))


def test_declared_size_mismatch_is_reported() -> None:
    """证伪：声明 1200×630、真实 1080×1440（竖版分享卡），必须报。"""
    problems, metrics = social.audit_image(fake_jpeg(1080, 1440), "image/jpeg", (1200, 630))
    assert any("不符" in p for p in problems), (problems, metrics)
    assert metrics["size"] == (1080, 1440)


def test_image_ok() -> None:
    problems, metrics = social.audit_image(fake_jpeg(1200, 630), "image/jpeg", (1200, 630))
    assert problems == [], problems
    assert metrics["size"] == (1200, 630)


def test_heavy_image_is_reported() -> None:
    """证伪：1.45MB（当年那张 PNG）超过抓取器预算。"""
    problems, metrics = social.audit_image(fake_jpeg(1200, 630, pad=1_450_000), "image/jpeg", (1200, 630))
    assert any("超过" in p and "KB" in p for p in problems), problems
    assert metrics["kb"] > 1000


def test_non_image_content_type_is_reported() -> None:
    problems, _ = social.audit_image(b"<html>404</html>", "text/html", None)
    assert any("Content-Type" in p for p in problems), problems


def test_real_og_card_matches_declared_size() -> None:
    """仓库里那张真图：像素必须等于页面声明的 1200×630（读了才发现，不靠记）。"""
    path = os.path.join(ROOT, "docs", "assets", "og-card.jpg")
    with open(path, "rb") as fh:
        data = fh.read()
    assert social.image_size(data) == (1200, 630)
    problems, _ = social.audit_image(data, "image/jpeg", (1200, 630))
    assert problems == [], problems


def test_declared_parser_tolerates_missing_fields() -> None:
    """只有 og:image、没写 width/height 时不该炸，也不该编一个尺寸出来。"""
    assert social._declared({"og:image": "x.jpg"}) is None
    assert social._declared({"og:image:width": "1200", "og:image:height": "630"}) == (1200, 630)
