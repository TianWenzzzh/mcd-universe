"""JS 星图模型与 Python 模型的一致性校验。

模板里内嵌了一份 JS 版模型（浏览器端「粘贴订单即生成」用），与 src/star_model.py
是同一套规则的两份实现。这个测试把两份实现喂同一批订单，逐字段比对，防止漂移。

做法：从 templates/starmap.html 抽取 `// [MODEL-BEGIN] ... // [MODEL-END]` 之间的代码，
拼成一段独立 Node 脚本执行，输出 JSON 与 Python 结果对比。

没有 node 时跳过（CI 的 ubuntu-latest 自带 node，本地 Windows 也有）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from star_model import build_starmap, detect_personality

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "templates", "starmap.html")
SAMPLES = os.path.join(ROOT, "samples")
NODE = shutil.which("node")


def _model_source() -> str:
    with open(TEMPLATE, encoding="utf-8") as f:
        src = f.read()
    start = src.index("// [MODEL-BEGIN]")
    end = src.index("// [MODEL-END]")
    return src[start:end]


def _python_result(orders: list) -> dict:
    sm = build_starmap(orders)
    stars = [{k: v for k, v in s.items() if k != "dt"} for s in sm.get("stars", [])]
    return {
        "status": sm["status"],
        "stars": stars,
        "summary": sm["summary"],
        "persona": detect_personality(sm) if sm["status"] == "galaxy" else None,
    }


def _js_result(orders: list, tmp_path) -> dict:
    script = (
        _model_source()
        + "\nvar orders = "
        + json.dumps(orders, ensure_ascii=False)
        + ";\n"
        + "var out = modelBuild(orders);\n"
        + "console.log(JSON.stringify(out));\n"
    )
    path = tmp_path / "model_run.js"
    path.write_text(script, encoding="utf-8")
    proc = subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"node 执行失败: {proc.stderr[:500]}"
    return json.loads(proc.stdout)


def _compare(orders: list, tmp_path, label: str) -> None:
    py = _python_result(orders)
    js = _js_result(orders, tmp_path)
    assert js["status"] == py["status"], f"{label}: status 不一致"
    assert js["summary"] == py["summary"], f"{label}: summary 不一致 {js['summary']} != {py['summary']}"
    assert len(js["stars"]) == len(py["stars"]), f"{label}: 星数不一致"
    for a, b in zip(js["stars"], py["stars"], strict=True):
        for key in ("id", "category", "color", "magnitude", "product", "store", "amount", "quantity", "time"):
            assert a.get(key) == b.get(key), f"{label}: 字段 {key} 不一致 {a.get(key)} != {b.get(key)}"
    js_persona = js["persona"]["name"] if js.get("persona") else None
    assert js_persona == py["persona"], f"{label}: 人格不一致 {js_persona} != {py['persona']}"


@pytest.mark.skipif(NODE is None, reason="未安装 node")
@pytest.mark.parametrize(
    "fname",
    ["demo_orders.json", "demo_orders_breakfast.json", "demo_orders_dessert.json", "demo_orders_burger.json"],
)
def test_js_matches_python_on_samples(fname, tmp_path):
    with open(os.path.join(SAMPLES, fname), encoding="utf-8") as f:
        _compare(json.load(f), tmp_path, fname)


@pytest.mark.skipif(NODE is None, reason="未安装 node")
def test_js_matches_python_on_edge_cases(tmp_path):
    cases = {
        "空列表": [],
        "单笔": [
            {
                "orderId": "E1",
                "createTime": "2026-10-24 20:26:00",
                "realTotalAmount": "27.4",
                "orderProductList": [{"productName": "龙焰鸡腿堡三件套", "quantity": 1}],
            },
        ],
        "无时间": [
            {"orderId": "E2", "realTotalAmount": 25, "orderProductList": [{"productName": "巨无霸", "quantity": 1}]},
        ],
        "无餐品": [
            {"orderId": "E3", "createTime": "2026-10-01 12:00:00", "realTotalAmount": "20", "orderProductList": []},
        ],
        "金额是数字/字符串混用": [
            {
                "orderId": "E4",
                "createTime": "2026-10-02 12:00:00",
                "realTotalAmount": 25.5,
                "orderProductList": [{"productName": "中薯条", "quantity": 2}],
            },
            {
                "orderId": "E5",
                "createTime": "2026-10-03 12:00:00",
                "realTotalAmount": "99.9",
                "orderProductList": [{"productName": "麦乐鸡", "quantity": 5}],
            },
        ],
        "深夜边界22点与2点": [
            {
                "orderId": "E6",
                "createTime": "2026-10-01 22:00:00",
                "realTotalAmount": "30",
                "orderProductList": [{"productName": "巨无霸", "quantity": 1}],
            },
            {
                "orderId": "E7",
                "createTime": "2026-10-02 02:59:00",
                "realTotalAmount": "30",
                "orderProductList": [{"productName": "巨无霸", "quantity": 1}],
            },
        ],
        "脏数据": [
            {
                "orderId": "E8",
                "createTime": "not-a-date",
                "realTotalAmount": "abc",
                "orderProductList": [{"productName": "咖啡", "quantity": None}],
            },
        ],
    }
    for label, orders in cases.items():
        _compare(orders, tmp_path, label)


@pytest.mark.skipif(NODE is None, reason="未安装 node")
def test_model_block_is_dom_free():
    """模型块必须与 DOM 无关，否则在 Node 里跑不起来，也说明分层被破坏。"""
    src = _model_source()
    for banned in ("document", "window", "getElementById", "localStorage"):
        assert banned not in src, f"模型块不应出现 {banned}"
