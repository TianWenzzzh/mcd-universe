"""MCP 客户端健壮性测试：重试退避、握手、null 转换。全部 mock 传输层，不打真实网络。"""

import io
import json
import os
import sys
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp_client import MCDClient, MCPError, extract_payload


def _http_response(payload):
    resp = io.BytesIO(json.dumps(payload).encode("utf-8"))
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda self, *a: None
    return resp


def _tool_result(data=None):
    return {"result": {"structuredContent": {"success": True, "data": data if data is not None else {}}}}


def test_retry_on_429_then_success():
    client = MCDClient(token="test", max_retries=2)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, None)
        return _http_response(_tool_result({"list": []}))

    with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch("time.sleep"):
        result = client.call_tool("order-list")
    assert result["success"] is True
    # 调用序列：initialize(429) → initialize(重试成功) → notifications/initialized → tools/call
    assert calls["n"] == 4, f"429 后必须重试，实际调用 {calls['n']} 次"


def test_non_retryable_http_error_raises_immediately():
    client = MCDClient(token="test", max_retries=3)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch("time.sleep"):
        try:
            client.call_tool("order-list")
            raise AssertionError("400 不应重试")
        except MCPError:
            pass
    assert calls["n"] == 1, "400 属于不可重试错误，必须立即抛出"


def test_initialize_handshake_before_first_tool_call():
    client = MCDClient(token="test")
    methods = []

    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        methods.append(body["method"])
        if body["method"] == "initialize":
            return _http_response({"result": {"capabilities": {}}})
        if body["method"] == "notifications/initialized":
            return _http_response({})
        return _http_response(_tool_result({"list": []}))

    with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch("time.sleep"):
        client.call_tool("order-list")
        client.call_tool("order-list")
    assert methods[0] == "initialize", "首个工具调用前必须完成 initialize"
    assert methods[1] == "notifications/initialized"
    assert methods.count("initialize") == 1, "握手只做一次"


def test_table_null_literal_becomes_none():
    table = {"content": [{"type": "text", "text": "[1]{productName,nutritionDescription}:\n  巨无霸,null\n"}]}
    rows = extract_payload(table)["data"]
    assert rows[0]["nutritionDescription"] is None, "字面量 null 必须转 None"
    assert rows[0]["productName"] == "巨无霸"


def test_retry_exhaustion_raises_mcp_error():
    client = MCDClient(token="test", max_retries=1)

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch("time.sleep"):
        try:
            client.call_tool("order-list")
            raise AssertionError("重试耗尽必须抛出 MCPError")
        except MCPError:
            pass


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
