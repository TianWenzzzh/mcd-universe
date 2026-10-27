"""产品主管线：MCP 拉订单 -> 星图模型 -> 注入模板 -> 输出 HTML 报告。

用法：
    # 演示模式（模拟数据，匿名化）
    python scripts/generate_report.py --demo samples/demo_orders.json -o demo/index.html
    # 真实模式（本地 MCP Token 拉取本人订单）
    export MCD_MCP_TOKEN="your_token"
    python scripts/generate_report.py --live -o report.html
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp_client import MCDClient, MCPError, parse_orders
from star_model import PERSONAS, build_starmap, detect_personality

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "starmap.html")
PLACEHOLDER = "__STARMAP_DATA__"


def load_orders_demo(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_daily(client) -> dict | None:
    """今日麦签：优先今天，其次最近未来，再次最近往期（不再默认取第一条）。"""
    try:
        cal = client.call_tool("campaign-calendar")
        daily = (cal.get("data") or {}).get("dailyList") or []
        today = (cal.get("data") or {}).get("currentTime", "")[:10]
        candidates = []
        for day in daily:
            for ev in day.get("events") or []:
                title = ((ev.get("articleDto") or {}).get("title") or "").strip()
                if title:
                    candidates.append({"date": day.get("date") or "", "title": title})
        for c in candidates:
            if c["date"] == today:
                return c
        future = [c for c in candidates if c["date"] > today]
        if future:
            return min(future, key=lambda c: c["date"])
        past = [c for c in candidates if c["date"] and c["date"] < today]
        if past:
            return max(past, key=lambda c: c["date"])
        return candidates[0] if candidates else None
    except (MCPError, AttributeError, KeyError):
        return None


def load_orders_live() -> tuple:
    client = MCDClient()
    orders = parse_orders(client.call_tool("order-list"))
    account = {}
    try:
        acc = client.call_tool("query-my-account")
        account = acc.get("data", {}) if isinstance(acc, dict) else {}
    except MCPError as e:
        print(f"积分查询跳过: {e}")
    daily = load_daily(client)
    return orders, account, daily


def render(
    starmap: dict, out_path: str, demo: bool = False, account: dict | None = None, daily: dict | None = None
) -> None:
    payload = {
        "status": starmap["status"],
        "stars": [{k: v for k, v in s.items() if k != "dt"} for s in starmap.get("stars", [])],
        "summary": starmap["summary"],
        "persona": None,
        "demo": demo,
        "account": account or None,
        "daily": daily,
    }
    if starmap["status"] == "galaxy":
        name = detect_personality(starmap)
        payload["persona"] = {"name": name, "desc": PERSONAS[name]}
    # 人格图鉴：全员亮相 + 自己的那枚高亮（单一数据源，图鉴与鉴定永不漂移）
    mine = payload["persona"]["name"] if payload["persona"] else None
    payload["personas"] = [{"name": n, "desc": d, "mine": n == mine} for n, d in PERSONAS.items()]

    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    if PLACEHOLDER not in html:
        raise SystemExit("模板中未找到数据占位符")
    html = html.replace(PLACEHOLDER, json.dumps(payload, ensure_ascii=False))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(
        f"报告已生成: {out_path}（{payload['summary']['orderCount']} 颗星"
        + (f"，人格：{payload['persona']['name']}" if payload["persona"] else "，星云状态）")
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", help="演示订单 JSON 路径")
    ap.add_argument("--live", action="store_true", help="通过 MCP 拉取本人真实订单")
    ap.add_argument("-o", "--out", default="report.html")
    args = ap.parse_args()

    account = None
    daily = None
    if args.live:
        orders, account, daily = load_orders_live()
        render(build_starmap(orders), args.out, demo=False, account=account, daily=daily)
    elif args.demo:
        orders = load_orders_demo(args.demo)
        render(build_starmap(orders), args.out, demo=True)
    else:
        ap.error("必须指定 --demo 或 --live")


if __name__ == "__main__":
    main()
