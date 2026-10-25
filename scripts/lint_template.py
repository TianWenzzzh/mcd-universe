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
    "URLSearchParams",
    "Image",
    "Uint8Array",
    "Error",
    "TypeError",
}


def main():
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()

    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    if not scripts:
        print("FAIL: 未找到主脚本")
        sys.exit(1)
    js = scripts[0]
    # 剥掉字符串字面量，避免把 "rgba(" 这类内容误判为函数调用
    js_code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', js)
    js_code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", js_code)

    # 1. 收集定义：函数声明 + var/let 函数表达式 + 方法调用不算
    defined = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", js_code))
    defined |= set(re.findall(r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:function|\()", js_code))
    defined |= BUILTINS

    called = set(re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", js_code))
    # 过滤明显的方法调用（前面带点）已在正则排除；再排除事件内联与关键字
    keywords = {"if", "for", "while", "switch", "catch", "return", "function", "typeof", "new"}
    undefined = sorted(n for n in called - defined - keywords if not n[0].isupper() or n in ("JSON",))

    # 2. DOM id 引用检查
    ids_in_html = set(re.findall(r'id="([^"]+)"', html))
    ids_used = set(re.findall(r'getElementById\("([^"]+)"\)', js))
    missing_ids = sorted(ids_used - ids_in_html)

    ok = True
    if undefined:
        ok = False
        print("FAIL 未定义函数调用:", ", ".join(undefined))
    if missing_ids:
        ok = False
        print("FAIL 引用了不存在的元素 id:", ", ".join(missing_ids))
    if ok:
        print(f"PASS 模板静态检查（{len(defined)} 个定义，{len(ids_used)} 个 DOM 引用全部存在）")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
