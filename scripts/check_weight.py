"""页面重量与外部依赖检查。

这个作品的承诺是"单文件、零依赖、断网也能跑"：评委点开链接的那一刻，
没有任何 CDN、字体、统计脚本在跟它抢带宽。这种承诺最容易被无意破坏 ——
加一个 webfont、换一个图表库、把截图直接内嵌成 base64，页面从 86KB 变成 800KB，
本地还看不出来（自己的网络太快）。

所以把它变成一条可执行的预算：
  - 单页字节上限；
  - 页面里不允许出现指向外部主机的 script / link / img / iframe（data: 与相对路径放行）。

用法：
    python scripts/check_weight.py          # 超预算返回 1
    python scripts/check_weight.py --json
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 预算：演示页 86KB 上下（单文件，含全部演示数据与渲染器），留 40% 余量。
# 说明页更轻；超过就说明有人把图片或库直接塞进去了。
BUDGET_KB = {
    "demo/index.html": 120,
    "demo/breakfast.html": 120,
    "demo/dessert.html": 120,
    "demo/burger.html": 120,
    "docs/about.html": 60,
}
DEFAULT_BUDGET_KB = 120

# 会发起网络请求的属性。srcset / poster 一并算上，不然换个属性名就漏了。
RES_RE = re.compile(
    r"""<(script|link|img|iframe|source|video|audio|embed|object)\b[^>]*?\b(href|src|srcset|data|poster)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
REMOTE_RE = re.compile(r"^(https?:)?//", re.IGNORECASE)


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


def check(root: str = ROOT) -> list[tuple[str, str]]:
    """返回 [(页面, 问题)]。空列表 = 全部达标。"""
    problems: list[tuple[str, str]] = []
    for rel in _pages(root):
        path = os.path.join(root, rel)
        size_kb = os.path.getsize(path) / 1024
        budget = BUDGET_KB.get(rel, DEFAULT_BUDGET_KB)
        if size_kb > budget:
            problems.append((rel, f"{size_kb:.0f}KB 超出预算 {budget}KB"))

        with open(path, encoding="utf-8", errors="replace") as fh:
            html = fh.read()
        for tag, attr, url in RES_RE.findall(html):
            u = url.strip()
            if not u or u.startswith("data:") or u.startswith("#"):
                continue
            if REMOTE_RE.match(u):
                problems.append((rel, f"<{tag} {attr}> 指向外部主机：{u[:60]}"))
    return problems


def report() -> int:
    as_json = "--json" in sys.argv
    problems = check()
    rows = []
    for rel in _pages(ROOT):
        rows.append((rel, round(os.path.getsize(os.path.join(ROOT, rel)) / 1024, 1)))
    if as_json:
        print(json.dumps({"pages": rows, "problems": problems}, ensure_ascii=False, indent=2))
    else:
        for rel, kb in rows:
            print(f"  {kb:>7.1f}KB  {rel}  (预算 {BUDGET_KB.get(rel, DEFAULT_BUDGET_KB)}KB)")
        if problems:
            print(f"\n页面重量检查失败（{len(problems)} 项）")
            for rel, why in problems:
                print(f"  ✗ {rel}: {why}")
        else:
            print(f"\nPASS 页面重量检查（{len(rows)} 页，均无外部依赖）")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(report())
