"""社交预览元信息检查。

为什么值得单独一个检查器：这个作品要被「转」出去 —— 转进评审群、转进朋友圈、
评委把链接发给同事。链接被贴出去的那一刻，别人看到的是抓取器读到的标题、
描述和缩略图，而不是页面本身。

而这类问题在本地完全看不出来：自己点开链接是正常的页面，只有别人手机里的那条
消息卡片是空白的。演示页早就有 og:meta，说明页一直没有 —— 它被当成"作品简介"
链接转发，转出去却是一张灰卡。

检查两件事：
  1. 每个页面都得有：theme-color / color-scheme / favicon / description /
     og:title / og:description / og:image / og:type / twitter:card；
  2. og:image 必须指向本仓库里真实存在的、够小的图片 —— 大图会被抓取器丢掉。
     曾经指向 submit-1.png（1.45MB），微信里经常只剩标题没有图。

用法：
    python scripts/check_meta.py
    python scripts/check_meta.py --json
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# og:image 必须是绝对地址，抓取器不认相对路径；绝对地址又要能映射回仓库里的文件，
# 所以站点的前缀固定成这一个（GitHub Pages 主站）。
SITE = "https://tianwenzzzh.github.io/mcd-universe/"

# 抓取器（微信/Telegram/Twitter）对缩略图有体积和超时上限，200KB 是安全线。
OG_MAX_KB = 200

# JPG / WebP 才是这个位置的正确格式：PNG 的截图动辄 1MB 以上。
OG_EXT = (".jpg", ".jpeg", ".webp")

META_RE = re.compile(
    r"""<meta\s+[^>]*?(?:property|name)\s*=\s*["']([^"']+)["'][^>]*?\bcontent\s*=\s*["']([^"']*)["']""", re.IGNORECASE
)
META_RE_REV = re.compile(
    r"""<meta\s+[^>]*?\bcontent\s*=\s*["']([^"']*)["'][^>]*?(?:property|name)\s*=\s*["']([^"']+)["']""", re.IGNORECASE
)
ICON_RE = re.compile(r"""<link\s+[^>]*?\brel\s*=\s*["'][^"']*\bicon\b[^"']*["']""", re.IGNORECASE)

REQUIRED_META = (
    "theme-color",
    "color-scheme",
    "description",
    "og:title",
    "og:description",
    "og:image",
    "og:type",
    # og:url 不是装饰：镜像上的页面必须声明镜像自己的地址，否则分享链接点在镜像、
    # 声明却说自己是 Pages（两套域名，抓取器按声明回抓，卡片就指到了另一台主机）。
    "og:url",
    "og:site_name",
    "twitter:card",
)


def _pages(root: str) -> list[str]:
    out = []
    for base in ("demo", "docs"):
        d = os.path.join(root, base)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".html"):
                out.append(f"{base}/{name}")
    return out


def metas(html: str) -> dict[str, str]:
    """把 <meta> 读成 {name: content}。两种属性顺序都要认。"""
    out: dict[str, str] = {}
    for key, val in META_RE.findall(html):
        out.setdefault(key.lower(), val.strip())
    for val, key in META_RE_REV.findall(html):
        out.setdefault(key.lower(), val.strip())
    return out


def check(root: str = ROOT) -> list[tuple[str, str]]:
    """返回 [(页面, 问题)]。空列表 = 全部达标。"""
    problems: list[tuple[str, str]] = []
    for rel in _pages(root):
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            html = fh.read()
        found = metas(html)

        for key in REQUIRED_META:
            if not found.get(key):
                problems.append((rel, f"缺少 <meta {key}>"))

        if not ICON_RE.search(html):
            problems.append((rel, "缺少 favicon（<link rel=icon>）"))

        og = found.get("og:image", "")
        if not og:
            continue
        # 相对路径抓取器不认；外站的图更要拦（这个项目的承诺是零外部主机）
        if not og.startswith(SITE):
            problems.append((rel, f"og:image 不是本站绝对地址：{og[:60]}"))
            continue
        target = os.path.join(root, og[len(SITE) :].replace("/", os.sep))
        if not os.path.isfile(target):
            problems.append((rel, f"og:image 指向的文件不存在：{og[len(SITE) :]}"))
            continue
        if not target.lower().endswith(OG_EXT):
            problems.append((rel, f"og:image 不是 JPG/WebP：{os.path.basename(target)}"))
        kb = os.path.getsize(target) / 1024
        if kb > OG_MAX_KB:
            problems.append((rel, f"og:image 体积 {kb:.0f}KB 超过 {OG_MAX_KB}KB，抓取器可能丢弃"))

        # og:url 指错的页面不会让任何东西变红，但分享出去的卡片会"回到另一页"。
        url = found.get("og:url", "")
        if url and not url.startswith(SITE):
            problems.append((rel, f"og:url 不是本站绝对地址：{url[:60]}"))
        elif url:
            target_page = url[len(SITE) :] or "index.html"
            if target_page.endswith("/"):
                target_page += "index.html"
            if not os.path.isfile(os.path.join(root, target_page.replace("/", os.sep))):
                problems.append((rel, f"og:url 指向的页面不存在：{target_page}"))
    return problems


def report() -> int:
    as_json = "--json" in sys.argv
    problems = check()
    if as_json:
        print(json.dumps({"problems": problems}, ensure_ascii=False, indent=2))
    elif problems:
        print(f"社交元信息检查失败（{len(problems)} 项）")
        for rel, why in problems:
            print(f"  ✗ {rel}: {why}")
    else:
        print(
            f"PASS 社交元信息检查（{len(_pages(ROOT))} 页：og / twitter / theme-color / favicon 齐全，缩略图 ≤{OG_MAX_KB}KB）"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(report())
