"""McUniverse MCP 客户端：对接麦当劳 MCP（Streamable HTTP）并归一化返回。

MCP 实际返回有三种形态（2026-10-22 实测）：
1. structuredContent 内干净 dict（query-my-account）
2. text 块包装 "## Original Response" + 内嵌 JSON（order-list / query-order）
3. text 表格 "[N]{col,col}:" + CSV 行（list-nutrition-foods）

extract_payload() 统一归一为 python 对象。Token 只从环境变量读取，禁止硬编码。
"""
import json
import os
import re
import urllib.request

MCP_URL = "https://mcp.mcd.cn"


class MCPError(Exception):
    pass


def check_business_error(payload, name):
    """业务错误检测：isError=false 但 success=false 的响应（实测 code 610301 非本人订单）。"""
    if isinstance(payload, dict) and payload.get("success") is False:
        raise MCPError(f"工具 {name} 业务错误 [{payload.get('code')}]: {payload.get('message')}")


class MCDClient:
    def __init__(self, token=None, url=MCP_URL):
        self.token = token or os.environ.get("MCD_MCP_TOKEN")
        if not self.token:
            raise MCPError("未设置 MCD_MCP_TOKEN 环境变量")
        self.url = url
        self._id = 0

    def _post(self, payload):
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _rpc(self, method, params=None):
        self._id += 1
        resp = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        if "error" in resp:
            raise MCPError(str(resp["error"]))
        return resp["result"]

    def list_tools(self):
        return self._rpc("tools/list").get("tools", [])

    def call_tool(self, name, args=None):
        result = self._rpc("tools/call", {"name": name, "arguments": args or {}})
        if result.get("isError"):
            raise MCPError(f"工具 {name} 返回错误: {result}")
        payload = extract_payload(result)
        check_business_error(payload, name)
        return payload


def _parse_table(text):
    """解析 "[N]{col,col}:" + CSV 行 的文本表格（list-nutrition-foods 的实际格式）。"""
    m = re.match(r"\[(\d+)\]\{([^}]*)\}:\s*\n(.*)", text.strip(), re.S)
    if not m:
        return None
    cols = [c.strip() for c in m.group(2).split(",")]
    rows = []
    for line in m.group(3).strip().splitlines():
        vals = [v.strip() for v in line.split(",")]
        rows.append(dict(zip(cols, vals)))
    return rows


def extract_payload(result):
    """把 MCP tool 结果归一化为 python 数据（兼容上述三种形态）。"""
    payload = None
    sc = result.get("structuredContent")
    if isinstance(sc, dict) and sc.get("data") is not None:
        payload = sc
    else:
        for block in result.get("content", []):
            if block.get("type") != "text":
                continue
            text = block["text"]
            m = re.search(r"## Original Response\s*\n(.+)", text, re.S)
            if m:
                # 标记后可能带人话提示再跟 JSON（错误响应实测如此），从第一个 { 起 raw_decode
                body = m.group(1)
                start = body.find("{")
                if start >= 0:
                    try:
                        payload, _ = json.JSONDecoder().raw_decode(body[start:])
                        break
                    except json.JSONDecodeError:
                        pass
            rows = _parse_table(text)
            if rows is not None:
                return {"data": rows}
        if payload is None:
            return result

    # 二层包装：JSON 的 data 字段本身又是文本表格（实测 list-nutrition-foods 即此形态）
    if isinstance(payload, dict) and isinstance(payload.get("data"), str):
        rows = _parse_table(payload["data"])
        if rows is not None:
            payload["data"] = rows
    return payload


def parse_orders(payload):
    """从 call_tool('order-list') 的归一化结果中取出订单列表。"""
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        orders = data.get("list")
        return orders if isinstance(orders, list) else []
    return []
