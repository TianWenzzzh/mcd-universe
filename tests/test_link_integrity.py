"""页面链接完整性测试：既验证仓库当前零死链，也验证检查器本身抓得住死链。

第二条是重点——一个永远 PASS 的检查器等于没有检查，所以先用一个明知有问题的
页面把检查器证伪：它必须报出那条 `../demo/` 解析失败。
"""

import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_checker():
    path = os.path.join(ROOT, "scripts", "check_links.py")
    spec = importlib.util.spec_from_file_location("check_links", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_links"] = module
    spec.loader.exec_module(module)
    return module


check_links = _load_checker()


def test_repo_has_no_broken_links():
    broken = check_links.check()
    detail = "；".join(f"{page}: {ref} -> {target}" for page, ref, target in broken)
    assert broken == [], f"发现死链：{detail}"


def test_checker_catches_broken_relative_link(tmp_path):
    """证伪：目录层级写错时必须报错（docs/ 下写 ./demo/ 会落到 docs/demo/）。"""
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "index.html").write_text("<html></html>", encoding="utf-8")
    (docs / "about.html").write_text('<a href="./demo/">体验</a>', encoding="utf-8")

    broken = check_links.check(str(tmp_path))
    assert len(broken) == 1
    assert broken[0][1] == "./demo/"


def test_checker_accepts_correct_link_and_ignores_external(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "index.html").write_text("<html></html>", encoding="utf-8")
    (docs / "about.html").write_text(
        '<a href="../demo/">体验</a>'
        '<a href="https://example.com/x">外链</a>'
        '<a href="#top">锚点</a>'
        '<img src="data:image/png;base64,AAA">'
        '<img src="../demo/index.html">',
        encoding="utf-8",
    )

    assert check_links.check(str(tmp_path)) == []
