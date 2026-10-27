"""镜像资源白名单守卫：页面会去取的图，必须真的传上去。

起因（2026-10-27 线上实测）：说明页与四个演示页的 `og:image` 都指向 `og-card.jpg`，
而镜像的白名单只认 `*-web.jpg` / `*-web.gif` / `.mp4` / `demo-poster.jpg` ——
`og-card.jpg` 从来没被上传，镜像链接转进微信就是一张灰卡，页面上也没人看得见。
这类"构建规则的遗漏"靠肉眼永远发现不了，只能让规则自己受检。
"""

from __future__ import annotations

import importlib.util
import io
import os
import re
import sys
import tarfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSET_RE = re.compile(r"assets/([A-Za-z0-9._-]+)")
PAGES = ["demo/index.html", "demo/breakfast.html", "demo/dessert.html", "demo/burger.html", "docs/about.html"]


def _load(name: str, rel: str):
    path = os.path.join(ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sync = _load("sync_mirror", os.path.join("deploy", "sync_mirror.py"))
check_meta = _load("check_meta", os.path.join("scripts", "check_meta.py"))
social = _load("check_social", os.path.join("scripts", "check_social.py"))


def kept(rel: str) -> bool:
    """白名单是否放行 docs/assets 下的这个文件。"""
    return sync._filter(tarfile.TarInfo(rel)) is not None


def referenced_assets() -> set[str]:
    names: set[str] = set()
    for page in PAGES:
        with open(os.path.join(ROOT, page), encoding="utf-8") as fh:
            for name in ASSET_RE.findall(fh.read()):
                names.add(name)
    return names


def test_every_referenced_asset_is_synced() -> None:
    missing = sorted(n for n in referenced_assets() if not kept(f"docs/assets/{n}"))
    assert missing == [], f"页面引用了但镜像不会上传：{missing}（改 deploy/sync_mirror.py 的 REFERENCED_ASSETS）"


def test_referenced_assets_exist_on_disk() -> None:
    missing = [n for n in sorted(referenced_assets()) if not os.path.isfile(os.path.join(ROOT, "docs", "assets", n))]
    assert missing == [], f"页面引用了不存在的文件：{missing}"


def test_bulk_originals_stay_off_the_mirror() -> None:
    """证伪：投稿用的大原图必须继续被拦下，否则白名单只是"全都放行"。"""
    assert kept("docs/assets/submit-1.png") is False
    assert kept("docs/assets/demo-detail.png") is False
    assert kept("docs/assets/demo.gif") is False
    # 对照：网页版与页面引用的小图必须放行
    assert kept("docs/assets/submit-1-web.jpg") is True
    assert kept("docs/assets/og-card.jpg") is True
    assert kept("docs/assets/demo-poster.jpg") is True
    assert kept("docs/assets/demo.mp4") is True


def test_html_and_demo_pages_are_not_filtered() -> None:
    """白名单只作用于 assets，页面本身一个都不能少。"""
    for page in PAGES:
        assert kept(page) is True


def test_mirror_html_declares_mirror_origin() -> None:
    """镜像页的 og:image / og:url 必须说镜像自己的地址（源文件写 Pages，上传的这份重写）。

    不重写的后果：抓取器为了取一张 72KB 的图要跨到 github.io，那台主机在国内时好时坏。
    """
    for page in PAGES:
        with open(os.path.join(ROOT, page), encoding="utf-8") as fh:
            src = fh.read()
        mirror = sync.rewrite_hosts(src)
        assert check_meta.SITE not in mirror, f"{page} 重写后仍残留 Pages 地址"
        assert sync.MIRROR_BASE in mirror, f"{page} 重写后没有镜像地址"
        page_url = sync.MIRROR_BASE + (page[: -len("index.html")] if page.endswith("index.html") else page)
        assert social.audit_page(mirror, page_url) == [], (page, social.audit_page(mirror, page_url))


def test_unrewritten_page_is_caught() -> None:
    """证伪：不重写的页面必须被判定抓出问题，否则上一条只是"永远 PASS"。"""
    with open(os.path.join(ROOT, "demo/index.html"), encoding="utf-8") as fh:
        src = fh.read()
    problems = social.audit_page(src, sync.MIRROR_BASE + "demo/")
    assert any("跨主机" in p for p in problems), problems


def test_tar_contains_rewritten_html_and_og_card() -> None:
    """真产物：打包出来的 HTML 已经是镜像口径，og-card 在包里。"""
    data = sync.build_tar()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        assert "docs/assets/og-card.jpg" in tar.getnames()
        html = tar.extractfile("demo/index.html").read().decode("utf-8")
    assert sync.MIRROR_BASE in html
    assert check_meta.SITE not in html
