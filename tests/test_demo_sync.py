"""演示页产物同步测试：模板改了、四个 demo 页没重建 —— 这类"产物落后于源码"是
旧文案、旧布局反复出现在线上页面的根源。

两条：
1. 仓库里四个演示页当前必须与 `templates/starmap.html` 完全同步；
2. 比较器本身要能被证伪：只改一个字的产物必须判为不同步，纯 CRLF 差异不能误报。
"""

import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_builder():
    path = os.path.join(ROOT, "scripts", "build_demo.py")
    spec = importlib.util.spec_from_file_location("build_demo", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_demo"] = module
    spec.loader.exec_module(module)
    return module


build_demo = _load_builder()


def test_demo_pages_cover_all_four_personas():
    pages = [page for _, page in build_demo.PAGES]
    assert pages == [
        "demo/index.html",
        "demo/breakfast.html",
        "demo/dessert.html",
        "demo/burger.html",
    ]
    for _, page in build_demo.PAGES:
        assert os.path.exists(os.path.join(ROOT, page)), f"缺少演示页 {page}"


def test_committed_demo_pages_match_template(tmp_path):
    """真实守卫：四个页面都必须是当前模板的产物。"""
    stale = []
    for sample, page in build_demo.PAGES:
        with open(os.path.join(ROOT, page), encoding="utf-8") as f:
            current = f.read()
        fresh_path = tmp_path / os.path.basename(page)
        build_demo.build_one(sample, fresh_path)
        with open(fresh_path, encoding="utf-8") as f:
            fresh = f.read()
        if build_demo.differs(fresh, current):
            stale.append(page)
    assert stale == [], f"演示页与模板不同步，请跑 scripts/build_demo.py：{stale}"


def test_comparator_flags_one_char_edit():
    """证伪：只改一个字也要报不同步，否则守卫形同虚设。"""
    base = "<h1>麦门宇宙</h1>"
    assert build_demo.differs(base.replace("宇宙", "星空"), base) is True


def test_comparator_ignores_crlf_only():
    """换行风格不是内容差异，不能误报（Windows 上检出即 CRLF）。"""
    assert build_demo.differs("a\r\nb", "a\nb") is False
