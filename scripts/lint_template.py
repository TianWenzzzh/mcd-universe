"""模板静态检查：抓两类只在运行时才暴露的 bug。

1. 未定义函数调用（如 layoutNebula 只有调用没有定义——星云态启动即崩）
2. JS 引用了 HTML 中不存在的元素 id

用法：python scripts/lint_template.py
"""

import os
import re
import sys

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "starmap.html")

BUILTINS = {
    "JSON",
    "Math",
    "Date",
    "Number",
    "String",
    "Object",
    "Array",
    "isNaN",
    "parseInt",
    "parseFloat",
    "document",
    "window",
    "performance",
    "location",
    "console",
    "requestAnimationFrame",
    "cancelAnimationFrame",
    "setTimeout",
    "clearTimeout",
    "setInterval",
    "clearInterval",
    "getComputedStyle",
    "matchMedia",
    "URLSearchParams",
    "Image",
    "Uint8Array",
    "Error",
    "TypeError",
}


def strip_noise(js: str) -> str:
    """剥掉字符串字面量与注释，只留下"真的会被执行"的代码。

    顺序很重要：先去字符串再去注释，否则字符串里的 `//` 会被当成注释开头。
    注释必须去掉——注释里写 `sqrt(ax²+ay²)` 这种说明，不是"调用了未定义的函数"。
    """
    code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', js)
    code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    return code


def scan(html: str) -> dict:
    """返回 {undefined, missing_ids, defined, ids_used}，列表均已排序。"""
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    if not scripts:
        return {"undefined": ["<未找到主脚本>"], "missing_ids": [], "defined": 0, "ids_used": 0}
    js = scripts[0]
    js_code = strip_noise(js)

    # 1. 收集定义：函数声明 + var/let 函数表达式 + 方法调用不算
    funcs = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", js_code))
    funcs |= set(re.findall(r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:function|\()", js_code))
    defined = funcs | BUILTINS

    called = set(re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", js_code))
    # 过滤明显的方法调用（前面带点）已在正则排除；再排除事件内联与关键字
    keywords = {"if", "for", "while", "switch", "catch", "return", "function", "typeof", "new"}
    undefined = sorted(n for n in called - defined - keywords if not n[0].isupper() or n in ("JSON",))

    # 2. DOM id 引用检查
    ids_in_html = set(re.findall(r'id="([^"]+)"', html))
    ids_used = set(re.findall(r'getElementById\("([^"]+)"\)', js))
    missing_ids = sorted(ids_used - ids_in_html)

    return {
        "undefined": undefined,
        "missing_ids": missing_ids,
        "defined": len(funcs),
        "ids_used": len(ids_used),
    }


def main() -> None:
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()

    res = scan(html)
    ok = True
    if res["undefined"]:
        ok = False
        print("FAIL 未定义函数调用:", ", ".join(res["undefined"]))
    if res["missing_ids"]:
        ok = False
        print("FAIL 引用了不存在的元素 id:", ", ".join(res["missing_ids"]))
    if ok:
        print(f"PASS 模板静态检查（{res['defined']} 个定义，{res['ids_used']} 个 DOM 引用全部存在）")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
