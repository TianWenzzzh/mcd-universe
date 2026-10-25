"""McUniverse MCP 客户端：对接麦当劳 MCP（Streamable HTTP）并归一化返回。

MCP 实际返回有三种形态（2026-10-22 实测）：
1. structuredContent 内干净 dict（query-my-account）
2. text 块包装 "## Original Response" + 内嵌 JSON（order-list / query-order）
3. text 表格 "[N]{col,col}:" + CSV 行（list-nutrition-foods）
extract_payload() 统一归一为 python 对象。

工程约定：
- Token 只从环境变量读取，禁止硬编码；
- 首次调用自动完成 initialize 握手与 notifications/initialized；
- 429/5xx/网络错误按指数退避重试（尊重 Retry-After），其余错误包装为 MCPError 抛出。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

MCP_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-03-26"
RETRYABLE_HTTP_CODES = (429, 500, 502, 503, 504)


class MCPError(Exception):
    """MCP 调用失败的统一异常（网络、协议、业务错误均归一到此）。"""


def check_business_error(payload: Any, name: str) -> None:
    """业务错误检测：isError=false 但 success=false 的响应（实测 code 610301 非本人订单）。"""
    if isinstance(payload, dict) and payload.get("success") is False:
        raise MCPError(f"工具 {name} 业务错误 [{payload.get('code')}]: {payload.get('message')}")


class MCDClient:
    """麦当劳 MCP 客户端（stdlib-only，无第三方依赖）。"""

    def __init__(
        self, token: str | None = None, url: str = MCP_URL, timeout: float = 30.0, max_retries: int = 3
    ) -> None:
        self.token = token or os.environ.get("MCD_MCP_TOKEN")
        if not self.token:
            raise MCPError("未设置 MCD_MCP_TOKEN 环境变量")
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries
        self._id = 0
        self._initialized = False

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            delay = min(0.5 * (2**attempt), 4.0)
            try:
                req = urllib.request.Request(
                    self.url,
                    data=data,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as e:
                last_err = MCPError(f"HTTP {e.code}: {e.reason}")
                if e.code not in RETRYABLE_HTTP_CODES:
                    raise last_err from e
                retry_after = e.headers.get("Retry-After") if e.headers else None
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        pass
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
                last_err = MCPError(f"网络错误: {e}")
            if attempt < self.max_retries:
                time.sleep(delay)
        assert last_err is not None
        raise last_err

    def _rpc(self, method: str, params: dict[str, Any] | None = None, notify: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notify:
            self._id += 1
            payload["id"] = self._id
        if params is not None:
            payload["params"] = params
        resp = self._post(payload)
        if notify:
            return {}
        if "error" in resp:
            raise MCPError(str(resp["error"]))
        return resp["result"]

    def _ensure_initialized(self) -> None:
        """按 MCP 规范完成 initialize 握手（服务端实测兼容，懒初始化只做一次）。"""
        if self._initialized:
            return
        self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcuniverse", "version": "1.0.0"},
            },
        )
        self._rpc("notifications/initialized", notify=True)
        self._initialized = True

    def list_tools(self) -> list[dict[str, Any]]:
        self._ensure_initialized()
        return self._rpc("tools/list").get("tools", [])

    def call_tool(self, name: str, args: dict[str, Any] | None = None) -> Any:
        self._ensure_initialized()
        result = self._rpc("tools/call", {"name": name, "arguments": args or {}})
        if result.get("isError"):
            raise MCPError(f"工具 {name} 返回错误: {result}")
        payload = extract_payload(result)
        check_business_error(payload, name)
        return payload


def _parse_table(text: str) -> list[dict[str, Any]] | None:
    """解析 "[N]{col,col}:" + CSV 行 的文本表格（list-nutrition-foods 的实际格式）。"""
    m = re.match(r"\[(\d+)\]\{([^}]*)\}:\s*\n(.*)", text.strip(), re.S)
    if not m:
        return None
    cols = [c.strip() for c in m.group(2).split(",")]
    rows = []
    for line in m.group(3).strip().splitlines():
        vals = [v.strip() for v in line.split(",")]
        # 字面量 "null" 与空串统一转 None，避免把字符串 null 当业务值用
        rows.append({c: (None if v in ("null", "") else v) for c, v in zip(cols, vals, strict=False)})
    return rows


def extract_payload(result: dict[str, Any]) -> Any:
    """把 MCP tool 结果归一化为 python 数据（兼容上述三种形态）。"""
    payload: Any = None
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


def parse_orders(payload: Any) -> list[dict[str, Any]]:
    """从 call_tool('order-list') 的归一化结果中取出订单列表。"""
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        orders = data.get("list")
        return orders if isinstance(orders, list) else []
    return []
