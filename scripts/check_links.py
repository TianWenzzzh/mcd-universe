"""链接完整性检查：抓「页面里写了 href/src 但目标不存在」的死链。

起因：`docs/about.html` 的主 CTA 写的是 `./demo/`，实际解析到 `docs/demo/` —— 线上 404。
所有测试与 E2E 都只跑 `demo/` 自身，没人检查页面之间的指向，于是这个死链活了下来。
这类 bug 完全可以静态查出来，不该靠人眼发现。

只检查仓库内的相对引用（GitHub Pages 部署后一一对应），外链、锚点、data URI 一律跳过。
目录引用（以 / 结尾）按 index.html 处理，与 Pages 行为一致。

用法：python scripts/check_links.py
"""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# templates/ 不参与：占位符模板会被注入到任意路径，其相对链接由生成的页面代表
SCAN_DIRS = ("demo", "docs")
HTML_EXT = (".html", ".htm")
SKIP_PREFIXES = ("http://", "https://", "//", "data:", "mailto:", "tel:", "javascript:", "#")
ATTR_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]*)"', re.IGNORECASE)


def html_files(root: str = ROOT) -> list[str]:
    pages = []
    for name in SCAN_DIRS:
        base = os.path.join(root, name)
        for dirpath, _dirnames, filenames in os.walk(base):
            for filename in sorted(filenames):
                if filename.lower().endswith(HTML_EXT):
                    pages.append(os.path.join(dirpath, filename))
    return pages


def resolve(page: str, ref: str, root: str = ROOT) -> str | None:
    """把页面内的引用解析成磁盘路径；不需要检查的引用返回 None。"""
    ref = ref.strip()
    if not ref or ref.lower().startswith(SKIP_PREFIXES):
        return None
    path = unquote(urlsplit(ref).path)
    if not path:
        return None
    if path.startswith("/"):
        # 站点根：GitHub Pages 项目站的根是仓库根，不是 demo/
        target = os.path.join(root, path.lstrip("/"))
    else:
        target = os.path.normpath(os.path.join(os.path.dirname(page), path))
    if path.endswith("/") or os.path.isdir(target):
        target = os.path.join(target, "index.html")
    return target


def check(root: str = ROOT) -> list[tuple[str, str, str]]:
    """返回 [(页面, 原始引用, 解析后的磁盘路径)]，空列表代表全部可达。"""
    broken = []
    for page in html_files(root):
        with open(page, encoding="utf-8") as f:
            html = f.read()
        for ref in ATTR_RE.findall(html):
            target = resolve(page, ref, root)
            if target is None or os.path.isfile(target):
                continue
            broken.append(
                (
                    os.path.relpath(page, root).replace(os.sep, "/"),
                    ref,
                    os.path.relpath(target, root).replace(os.sep, "/"),
                )
            )
    return broken


def main() -> None:
    broken = check()
    for page, ref, target in broken:
        print(f"FAIL {page}: {ref} -> {target} 不存在")
    if broken:
        print(f"共 {len(broken)} 处死链")
        sys.exit(1)
    print(f"PASS 链接检查（{len(html_files())} 个页面，本地引用全部可达）")


if __name__ == "__main__":
    main()
