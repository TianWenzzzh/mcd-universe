"""模板静态检查器自身的测试。

lint_template.py 是"防 layoutNebula 那类 ReferenceError"的护栏，但护栏本身也可能
看错东西：上一轮它就把注释里的 `sqrt(ax²+ay²)` 当成了未定义函数调用，把一次正常提交
拦了下来（假阳性）。所以这里两个方向都测：

1. 真 bug 必须报（只有调用没有定义的函数、引用不存在的 id）
2. 假 bug 必须不报（注释里的函数样式文本、字符串里的括号）
"""

import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_linter():
    path = os.path.join(ROOT, "scripts", "lint_template.py")
    spec = importlib.util.spec_from_file_location("lint_template", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint_template"] = module
    spec.loader.exec_module(module)
    return module


lint_template = _load_linter()


def _page(js: str, html: str = '<div id="sky"></div>') -> str:
    return f"<html><body>{html}<script>{js}</script></body></html>"


def test_repo_template_is_clean():
    with open(os.path.join(ROOT, "templates", "starmap.html"), encoding="utf-8") as f:
        res = lint_template.scan(f.read())
    assert res["undefined"] == [], f"未定义函数：{res['undefined']}"
    assert res["missing_ids"] == [], f"引用了不存在的 id：{res['missing_ids']}"


def test_catches_call_without_definition():
    """证伪方向一：只有调用、没有定义，必须报出来（layoutNebula 就是这么崩的）。"""
    res = lint_template.scan(_page("layoutNebula(1);"))
    assert "layoutNebula" in res["undefined"]


def test_catches_missing_element_id():
    """证伪方向二：getElementById 指向 HTML 里不存在的 id，必须报。"""
    res = lint_template.scan(_page('document.getElementById("nope").style;'))
    assert res["missing_ids"] == ["nope"]


def test_ignores_function_like_text_in_comments():
    """假阳性方向：注释里的 `sqrt(...)` 只是说明文字，不是调用。"""
    res = lint_template.scan(
        _page("/* 半径是 sqrt(ax²+ay²) */\n// 也有 pointLen(dx, dy) 这种写法\nfunction ok() { return 1; }\nok();")
    )
    assert res["undefined"] == []


def test_ignores_parens_inside_strings():
    """字符串里的括号同样是文字：'rgba(0,0,0,.5)' 不该被当成函数。"""
    res = lint_template.scan(_page('function p() { return "rgba(0,0,0,.5)"; }\np();'))
    assert res["undefined"] == []
