"""开发期数据拉取脚本：把 MCP 真实返回固化为 samples/ 下的干净 JSON。

用法：
    export MCD_MCP_TOKEN="your_token"
    python scripts/fetch_data.py

安全：Token 只从环境变量读；订单等个人数据只落本地 samples/，已被 .gitignore 排除。
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp_client import MCDClient, parse_orders

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")


def main():
    client = MCDClient()
    os.makedirs(SAMPLES_DIR, exist_ok=True)

    tools = client.list_tools()
    with open(os.path.join(SAMPLES_DIR, "mcp_tools.json"), "w", encoding="utf-8") as f:
        json.dump(
            [{"name": t["name"], "description": t.get("description", "")} for t in tools],
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"tools: {len(tools)} -> samples/mcp_tools.json")

    nutrition = client.call_tool("list-nutrition-foods")
    with open(os.path.join(SAMPLES_DIR, "nutrition_foods.json"), "w", encoding="utf-8") as f:
        json.dump(nutrition.get("data", []), f, ensure_ascii=False, indent=2)
    print(f"nutrition items: {len(nutrition.get('data', []))} -> samples/nutrition_foods.json")

    orders = parse_orders(client.call_tool("order-list"))
    with open(os.path.join(SAMPLES_DIR, "orders.local.json"), "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)
    print(f"orders: {len(orders)} -> samples/orders.local.json（本地数据，不入库）")

    account = client.call_tool("query-my-account")
    print("account data:", json.dumps(account.get("data", {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
