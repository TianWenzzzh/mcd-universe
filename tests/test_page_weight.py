"""页面重量预算测试：守住"单文件、零依赖"这条产品承诺。

和链接检查一样，先把检查器证伪 —— 一个不认外部脚本的检查器等于没有检查。
"""

import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load():
    path = os.path.join(ROOT, "scripts", "check_weight.py")
    spec = importlib.util.spec_from_file_location("check_weight", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_weight"] = module
    spec.loader.exec_module(module)
    return module


cw = _load()


def test_repo_pages_within_budget():
    problems = cw.check()
    detail = "；".join(f"{page}: {why}" for page, why in problems)
    assert problems == [], f"页面超出重量预算或引入外部依赖：{detail}"


def test_detects_remote_script(tmp_path):
    """证伪：塞一个 CDN 脚本进去，必须报外部依赖。"""
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "index.html").write_text(
        '<html><head><script src="https://cdn.example.com/lib.js"></script></head></html>',
        encoding="utf-8",
    )
    problems = cw.check(str(tmp_path))
    assert len(problems) == 1
    assert "外部主机" in problems[0][1]


def test_detects_remote_image_and_webfont(tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "index.html").write_text(
        '<link rel="stylesheet" href="//fonts.example.com/a.css"><img src="https://img.example.com/a.png">',
        encoding="utf-8",
    )
    problems = cw.check(str(tmp_path))
    assert len(problems) == 2, problems


def test_detects_oversize_page(tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "index.html").write_text("<html>" + "x" * (130 * 1024) + "</html>", encoding="utf-8")
    problems = cw.check(str(tmp_path))
    assert any("超出预算" in why for _, why in problems)


def test_allows_relative_data_and_anchor(tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "index.html").write_text(
        '<html><body><img src="data:image/png;base64,AAA">'
        '<a href="#top">锚点</a><img src="../docs/assets/qr.png"'
        ' crossorigin="anonymous" title="https://not-a-resource.example.com"></body></html>',
        encoding="utf-8",
    )
    assert cw.check(str(tmp_path)) == []
