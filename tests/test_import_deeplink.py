"""深链入口测试：`?open=import` 是"没有 Token 的人"唯一的三步入口。

背景：在线生成做好了，但入口藏在演示页右上角一行小字里 —— 评委从说明页点进来，
看到的是一段 2.5 秒的入场动画，然后是一片星图，没有任何提示说"你也能换成自己的订单"。
所以把入口提成一条可分享的链接：`demo/?open=import` 落地即开面板。

这里钉住四件事：
1. 模板确实认这个参数，并且带参数时首访引导不许再弹（否则 5.2 秒后它盖在面板上）；
2. 生成成功后要把参数从地址栏摘掉（刷新不该又弹一次）；
3. 说明页与 README 都得有这条链接，且指向真实存在的目录；
4. 检查器能证伪 —— 少一个字符、多一层目录都必须报错。
"""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HREF_RE = re.compile(r'href="([^"]*)"')


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def deeplinks(html: str) -> list[str]:
    """页面里所有指向「直开粘贴面板」的链接（按查询参数判断，不做子串匹配）。"""
    return [h for h in HREF_RE.findall(html) if parse_qs(urlsplit(h).query).get("open") == ["import"]]


def resolve(page_rel: str, href: str) -> str:
    """把链接解析成站点内的相对目录（去掉 query/fragment）。"""
    path = href.split("?")[0].split("#")[0]
    base = os.path.dirname(page_rel)
    return os.path.normpath(os.path.join(base, path)).replace(os.sep, "/")


def test_template_reads_open_param() -> None:
    tpl = _read("templates/starmap.html")
    assert 'PARAMS.get("open") === "import"' in tpl
    # 面板必须真的被打开，而不是只认了参数
    assert "if (OPEN_IMPORT) {" in tpl
    assert "importOpen(true)" in tpl


def test_onboarding_yields_to_deeplink() -> None:
    """带 open=import 时首访引导不许排进定时器：两套模态叠在一起会抢焦点。"""
    tpl = _read("templates/starmap.html")
    assert "var onboardTimer = !obSeen() && !OPEN_IMPORT;" in tpl


def test_deeplink_is_cleared_after_import() -> None:
    tpl = _read("templates/starmap.html")
    assert "history.replaceState" in tpl


@pytest.mark.parametrize("page", ["demo/index.html", "demo/breakfast.html", "demo/dessert.html", "demo/burger.html"])
def test_built_pages_carry_the_deeplink_logic(page: str) -> None:
    html = _read(page)
    assert 'PARAMS.get("open") === "import"' in html, f"{page} 未随模板重建"
    assert "onboardTimer = !obSeen() && !OPEN_IMPORT" in html


def test_about_page_links_to_import_panel() -> None:
    links = deeplinks(_read("docs/about.html"))
    assert links, "说明页没有任何「用自己的订单生成」入口"
    for href in links:
        target = resolve("docs/about.html", href)
        assert target == "demo", f"说明页的深链指向了 {target}，应为 demo"
        assert os.path.isfile(os.path.join(ROOT, target, "index.html")), f"{target}/index.html 不存在"


def test_readme_links_to_import_panel() -> None:
    """README 是 Markdown，链接写在 `[文案](url)` 里，不能拿 href 去找。"""
    md_links = re.findall(r"\]\((https?://[^)\s]+)\)", _read("README.md"))
    assert any(parse_qs(urlsplit(u).query).get("open") == ["import"] for u in md_links), "README 没有指向粘贴面板的深链"


def test_link_checker_flags_wrong_directory(tmp_path) -> None:
    """证伪：说明页若把深链写成 `./demo/?open=import`（相对 docs/ 就是 docs/demo/），
    链接检查器必须报死链。参数不能被当成"外链"跳过。"""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("check_links", os.path.join(ROOT, "scripts", "check_links.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_links"] = module
    spec.loader.exec_module(module)

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "about.html").write_text('<a href="./demo/?open=import">x</a>', encoding="utf-8")
    broken = module.check(str(tmp_path))
    assert broken, "带 query 的错误路径没有被判为死链"

    # 换成正确路径后必须放过 —— 否则检查器只是"永远报错"
    (docs / "about.html").write_text('<a href="../demo/?open=import">x</a>', encoding="utf-8")
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "index.html").write_text("<html></html>", encoding="utf-8")
    assert module.check(str(tmp_path)) == []


def test_deeplink_detector_can_fail() -> None:
    """证伪：参数拼错一个字符就必须找不到，不能靠子串蒙对。"""
    assert deeplinks('<a href="../demo/?open=import">x</a>') == ["../demo/?open=import"]
    assert deeplinks('<a href="../demo/?open=importt">x</a>') == []
    assert deeplinks('<a href="../demo/?open=export">x</a>') == []
    assert deeplinks('<a href="../demo/">x</a>') == []
