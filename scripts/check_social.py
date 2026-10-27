"""社交卡片抓取自检：把「链接被贴出去长什么样」量成数字。

为什么值得单独一个脚本：这一层的问题在自己的浏览器里永远看不见 ——
自己点开链接是完好的页面，只有别人手机里那条消息的卡片才是坏的。
坏得还很安静：标题在、描述在，缩略图那块空着。

2026-10-27 实测抓到的一件事：镜像（国内主链）的页面把 og:image 写成 GitHub Pages 的绝对地址，
而同一张图在镜像上本来就是有的（200 / 72,778B / 0.23s 热态）。抓取器为了取一张 72KB 的图
要跨到 github.io 去，那台主机在国内时好时坏 —— 卡片的图就成了抽奖。
镜像页的 og:url 也有同样的问题：链接点在镜像，声明说是 Pages。

检查分两段，判定和取数分离（这样 CI 里没有网络也能测判定逻辑）：
  1. 页面段（纯字符串）：og:title / og:description / og:image / og:type / og:url 齐全；
     og:image 与 og:url 必须与页面同主机；标题/描述不超卡片显示的字符数；
  2. 图片段（发一次请求）：状态、Content-Type、体积、真实像素与声明是否一致、耗时是否在预算内。

用法：
    python scripts/check_social.py                      # 默认查国内镜像
    python scripts/check_social.py --base https://tianwenzzzh.github.io/mcd-universe/
    python scripts/check_social.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 复用 check_meta 的 meta 解析：同一件事不要写第二份实现（这个仓库已经栽过"两份实现漂移"）。
from check_meta import metas  # noqa: E402

DEFAULT_BASE = "http://47.114.38.125/mcd/"
PAGES = ("demo/", "docs/about.html")

# 微信内置浏览器的真实 UA。抓取器对 UA 有分流，用桌面 UA 测不到真实那条路。
WEIXIN_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 MicroMessenger/8.0.49(0x18003128) NetType/WIFI Language/zh_CN"
)

OG_MAX_KB = 200  # 与 check_meta 同一条安全线
FETCH_BUDGET_S = 3.0  # 抓取器普遍在 3–5s 放弃；这里按更严的一头卡
TITLE_MAX = 64  # 卡片标题一行放得下的量级（中文字符计）
DESC_MAX = 120


def image_size(data: bytes) -> tuple[int, int] | None:
    """从文件头读像素尺寸，不依赖任何图像库（CI 与镜像服务器都不装 Pillow）。"""
    if data[:2] == b"\xff\xd8":  # JPEG：往后找 SOFn 段
        i, n = 2, len(data)
        while i + 9 < n:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = int.from_bytes(data[i + 2 : i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = int.from_bytes(data[i + 5 : i + 7], "big")
                w = int.from_bytes(data[i + 7 : i + 9], "big")
                return (w, h)
            i += 2 + seg
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return (w, h)
        if chunk == b"VP8L" and len(data) >= 25:
            bits = int.from_bytes(data[21:25], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        if chunk == b"VP8 " and len(data) >= 30:
            w = int.from_bytes(data[26:28], "little") & 0x3FFF
            h = int.from_bytes(data[28:30], "little") & 0x3FFF
            return (w, h)
    return None


def audit_page(html: str, page_url: str) -> list[str]:
    """页面段：只读字符串。返回问题列表，空 = 达标。"""
    m = metas(html)
    out: list[str] = []
    for key in ("og:title", "og:description", "og:image", "og:type", "og:url"):
        if not m.get(key):
            out.append(f"缺少 <meta {key}>")

    page = urlsplit(page_url)
    for key in ("og:image", "og:url"):
        val = m.get(key, "")
        if not val:
            continue
        u = urlsplit(val)
        if not u.scheme or not u.netloc:
            out.append(f"{key} 是相对地址，抓取器不认：{val[:60]}")
            continue
        if u.hostname != page.hostname:
            out.append(f"{key} 跨主机：页面在 {page.hostname}，目标在 {u.hostname}（抓取器要多跨一站，国内常取不到）")
        if u.scheme == "http" and page.scheme == "https":
            out.append(f"{key} 是 http 而页面是 https，部分平台会按混合内容丢弃")

    title = m.get("og:title", "")
    if len(title) > TITLE_MAX:
        out.append(f"og:title {len(title)} 字，超过卡片一行（{TITLE_MAX}）")
    desc = m.get("og:description", "")
    if len(desc) > DESC_MAX:
        out.append(f"og:description {len(desc)} 字，超过卡片两行（{DESC_MAX}）")
    return out


def audit_image(
    data: bytes,
    content_type: str,
    declared: tuple[int, int] | None,
    max_kb: int = OG_MAX_KB,
) -> tuple[list[str], dict]:
    """图片段：只读字节。返回（问题列表, 指标）。"""
    out: list[str] = []
    ct = (content_type or "").split(";")[0].strip().lower()
    if not ct.startswith("image/"):
        out.append(f"Content-Type 不是图片：{ct or '空'}")
    kb = len(data) / 1024
    if kb > max_kb:
        out.append(f"图片 {kb:.0f}KB 超过 {max_kb}KB，抓取器可能直接丢弃")
    size = image_size(data)
    if size is None:
        out.append("读不出像素尺寸（不是 JPEG/WebP）")
    elif declared and tuple(declared) != size:
        out.append(f"声明尺寸 {declared[0]}x{declared[1]} 与真实 {size[0]}x{size[1]} 不符")
    return out, {"bytes": len(data), "kb": round(kb, 1), "size": size, "content_type": ct}


def fetch(url: str, ua: str = WEIXIN_UA, timeout: float = 15.0) -> tuple[int, bytes, str, float]:
    """取一次 URL，返回（状态码, 字节, Content-Type, 耗时秒）。4xx/5xx 也当结果返回。"""
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, body, resp.headers.get("Content-Type", ""), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, b"", e.headers.get("Content-Type", "") if e.headers else "", time.monotonic() - t0
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, b"", f"连接失败：{e}", time.monotonic() - t0


def _declared(m: dict) -> tuple[int, int] | None:
    try:
        w, h = int(m.get("og:image:width", "")), int(m.get("og:image:height", ""))
    except ValueError:
        return None
    return (w, h) if w > 0 and h > 0 else None


def check_base(base: str, as_json: bool = False) -> list[dict]:
    """对一个站点前缀跑完整自检，返回每条页面的记录。"""
    if not base.endswith("/"):
        base += "/"
    rows: list[dict] = []
    for rel in PAGES:
        page_url = base + rel
        status, body, ctype, took = fetch(page_url)
        row: dict = {"page": page_url, "status": status, "bytes": len(body), "took": round(took, 2), "problems": []}
        if status != 200:
            row["problems"].append(f"页面取不到：HTTP {status} {ctype}")
            rows.append(row)
            continue
        html = body.decode("utf-8", "replace")
        m = metas(html)
        row["problems"] += audit_page(html, page_url)

        img = m.get("og:image", "")
        if img:
            istatus, idata, ict, itook = fetch(img)
            row["image"] = {"url": img, "status": istatus, "took": round(itook, 2)}
            if istatus != 200:
                row["problems"].append(f"og:image 取不到：HTTP {istatus}")
            else:
                p, metrics = audit_image(idata, ict, _declared(m))
                row["image"].update(metrics)
                row["problems"] += p
                if itook > FETCH_BUDGET_S:
                    row["problems"].append(f"og:image 耗时 {itook:.1f}s 超过抓取预算 {FETCH_BUDGET_S}s")
        row["title"] = m.get("og:title", "")
        rows.append(row)
        if not as_json:
            _print_row(row, m)
    return rows


def _print_row(row: dict, m: dict) -> None:
    print(f"  {row['page']}")
    if row["status"] != 200:
        print(f"    ✗ HTTP {row['status']}")
        return
    print(f"    页面 200 {row['bytes'] / 1024:.0f}KB {row['took']}s · 标题 {len(row.get('title', ''))} 字")
    img = row.get("image") or {}
    if img:
        size = img.get("size")
        dims = f"{size[0]}x{size[1]}" if size else "尺寸未知"
        print(f"    图 {img['status']} {img.get('content_type', '')} {img.get('kb', 0)}KB {dims} {img.get('took', 0)}s")
    for why in row["problems"]:
        print(f"    ✗ {why}")


def main() -> int:
    ap = argparse.ArgumentParser(description="社交卡片抓取自检")
    ap.add_argument("--base", action="append", help=f"站点前缀（可多次），默认 {DEFAULT_BASE}")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    bases = args.base or [DEFAULT_BASE]

    all_rows: list[dict] = []
    for base in bases:
        if not args.json:
            print(f"抓取器视角（微信 UA）· {base}")
        all_rows += check_base(base, args.json)

    problems = [(r["page"], why) for r in all_rows for why in r["problems"]]
    if args.json:
        print(json.dumps({"problems": problems, "rows": all_rows}, ensure_ascii=False, indent=2))
    elif problems:
        print(f"FAIL 抓取自检（{len(problems)} 项问题 / {len(all_rows)} 页）")
        for page, why in problems:
            print(f"  ✗ {page}: {why}")
    else:
        print(
            f"PASS 抓取自检（{len(all_rows)} 页 · 图与页同源 · ≤{OG_MAX_KB}KB · ≤{FETCH_BUDGET_S}s · 像素与声明一致）"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
