"""星图引擎测试：先证伪再交付。覆盖零单降级、三类 MCP 返回格式、人格鉴定分支。"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp_client import MCPError, check_business_error, extract_payload, parse_orders
from star_model import PERSONAS, build_starmap, categorize, detect_personality


def test_zero_orders_nebula():
    sm = build_starmap([])
    assert sm["status"] == "nebula", "0 单必须降级为星云状态而不是报错"
    assert sm["stars"] == []
    assert detect_personality(sm) == "麦门旅人"


def test_parse_orders_empty_data():
    assert parse_orders({"success": True, "data": {}}) == []
    assert parse_orders({"success": True, "data": {"list": None}}) == []


def _order(oid, name, amount, time, store="中北大学店"):
    return {
        "orderId": oid,
        "orderType": "1",
        "createTime": time,
        "storeName": store,
        "orderStatus": "已完成",
        "realTotalAmount": amount,
        "orderProductList": [{"productCode": "P1", "productName": name, "quantity": 1}],
    }


def test_starmap_galaxy():
    orders = [
        _order("A2", "巨无霸", "25.5", "2026-10-01 22:30:00"),
        _order("A1", "薯条", "12.0", "2026-09-15 12:00:00"),
        _order("A3", "朱古力新地", "15.0", "2026-10-10 23:10:00"),
    ]
    sm = build_starmap(orders)
    assert sm["status"] == "galaxy"
    assert sm["summary"]["orderCount"] == 3
    assert sm["summary"]["totalAmount"] == 52.5
    # 按时间排序：A1 最早
    assert sm["stars"][0]["id"] == "A1"
    # 品类判定
    cats = {s["id"]: s["category"] for s in sm["stars"]}
    assert cats["A2"] == "汉堡" and cats["A1"] == "小食" and cats["A3"] == "甜品"
    # 星等封顶 5
    assert all(1 <= s["magnitude"] <= 5 for s in sm["stars"])


def test_personality_night():
    orders = [_order(f"N{i}", "麦乐鸡", "20", f"2026-10-0{i + 1} 23:30:00") for i in range(3)]
    name = detect_personality(build_starmap(orders))
    assert name == "深夜麦门人", f"夜间订单应鉴定为深夜麦门人，实际 {name}"
    assert PERSONAS[name]


def test_personality_dessert():
    orders = [_order(f"D{i}", "圆筒冰淇淋", "8", f"2026-10-0{i + 1} 15:00:00") for i in range(3)] + [
        _order("D9", "巨无霸", "25", "2026-10-09 15:00:00")
    ]
    name = detect_personality(build_starmap(orders))
    assert name == "甜点星住民"


def test_categorize_rules():
    assert categorize("巨无霸汉堡") == "汉堡"
    assert categorize("龙焰鸡腿堡三件套") == "汉堡"  # 真实订单实测：腿堡系必须归汉堡
    assert categorize("麦辣鸡腿堡套餐") == "汉堡"
    assert categorize("中薯条") == "小食"
    assert categorize("朱古力新地") == "甜品"
    assert categorize("可口可乐") == "饮品"
    assert categorize("猪柳蛋麦满分") == "早餐"
    assert categorize("不认识的餐品") == "小食"  # 兜底


def test_extract_payload_three_formats():
    # 形态1：structuredContent 干净 dict
    r1 = {"structuredContent": {"success": True, "data": {"availablePoint": "0"}}}
    assert extract_payload(r1)["data"]["availablePoint"] == "0"

    # 形态2：text 包装 + 内嵌 JSON
    wrapped = {
        "content": [
            {
                "type": "text",
                "text": '# API Response Information\n\n## Original Response\n{"success":true,"data":{"list":[{"orderId":"X"}]}}',
            }
        ]
    }
    assert extract_payload(wrapped)["data"]["list"][0]["orderId"] == "X"

    # 形态3：text 表格
    table = {"content": [{"type": "text", "text": "[2]{productName,energyKcal}:\n  巨无霸,534\n  薯条,289\n"}]}
    rows = extract_payload(table)["data"]
    assert len(rows) == 2 and rows[0]["productName"] == "巨无霸" and rows[0]["energyKcal"] == "534"

    # 形态4（实测坑）：text 包装 JSON，其 data 字段又是文本表格——两层包装
    nested = {
        "content": [
            {
                "type": "text",
                "text": "# API Response Information\n\n## Original Response\n"
                + json.dumps({"success": True, "data": "[2]{productName,energyKcal}:\n  巨无霸,534\n  薯条,289\n"}),
            }
        ]
    }
    rows4 = extract_payload(nested)["data"]
    assert isinstance(rows4, list) and len(rows4) == 2, f"二层表格解析失败: {type(rows4)}"
    assert rows4[1]["productName"] == "薯条"


def test_extract_payload_error_text_with_prose():
    """实测坑：错误响应在 Original Response 标记后先输出人话提示再跟 JSON。"""
    err_text = (
        "# API Response Information\n\n## Original Response\n\n"
        "如果这个链接不为空，把lockerQrCode这个链接， 用![alt](lockerQrCode) 格式渲染\n"
        '{"success":false,"code":610301,"message":"非本人订单无法查询！"}'
    )
    payload = extract_payload({"content": [{"type": "text", "text": err_text}]})
    assert payload["success"] is False and payload["code"] == 610301


def test_business_error_detection():
    """isError=false 但 success=false 的业务错误必须被捕获，不允许静默通过。"""
    try:
        check_business_error({"success": False, "code": 610301, "message": "非本人订单无法查询！"}, "query-order")
        raise AssertionError("应当抛出 MCPError")
    except MCPError as e:
        assert "610301" in str(e)
    # 正常响应不抛
    check_business_error({"success": True, "data": {}}, "query-order")


def test_magnitude_clamped_1_to_5():
    sm = build_starmap([_order("H1", "巨无霸", "999", "2026-10-01 12:00:00")])
    assert sm["stars"][0]["magnitude"] == 5
    sm2 = build_starmap([_order("H2", "可口可乐", "0", "2026-10-01 12:00:00")])
    assert sm2["stars"][0]["magnitude"] >= 1


def test_malformed_time_no_crash():
    orders = [
        _order("M1", "薯条", "12", "not-a-date"),
        _order("M2", "可乐", "11", "2026-10-02 12:00:00"),
    ]
    sm = build_starmap(orders)
    assert len(sm["stars"]) == 2  # 坏时间不炸，星点照出
    detect_personality(sm)  # 坏时间不炸人格鉴定


def test_single_order():
    sm = build_starmap([_order("S1", "麦辣鸡腿堡套餐", "32", "2026-10-05 18:50:00")])
    assert sm["status"] == "galaxy" and sm["summary"]["orderCount"] == 1
    assert detect_personality(sm) in PERSONAS


def test_order_without_products():
    order = {"orderId": "NP1", "createTime": "2026-10-05 18:50:00", "realTotalAmount": "20", "orderProductList": []}
    sm = build_starmap([order])
    assert sm["stars"][0]["category"] == "小食"  # 无餐品走兜底品类
    assert sm["stars"][0]["quantity"] == 0


def test_persona_burger_and_explorer():
    burgers = [_order(f"B{i}", "巨无霸套餐", "25", f"2026-10-0{i + 1} 12:00:00") for i in range(3)]
    assert detect_personality(build_starmap(burgers)) == "硬核堡星人"
    varied = [
        _order(f"V{i}", n, "15", f"2026-10-0{i + 1} 12:00:00")
        for i, n in enumerate(["巨无霸", "中薯条", "朱古力新地", "可口可乐", "麦乐鸡", "猪柳蛋麦满分套餐"])
    ]
    assert detect_personality(build_starmap(varied)) == "麦门探索者"


def test_persona_morning_and_weekend():
    mornings = [_order(f"AM{i}", "猪柳蛋麦满分套餐", "16", f"2026-10-0{i + 1} 08:15:00") for i in range(3)]
    assert detect_personality(build_starmap(mornings)) == "早餐先行者"
    # 2026-10-17/18 是周六日；再补一个非凌晨非早晨的周六单
    weekends = [
        _order(f"WE{i}", "巨无霸套餐", "25", t)
        for i, t in enumerate(["2026-10-17 12:00:00", "2026-10-18 12:00:00", "2026-10-11 12:00:00"])
    ]
    assert detect_personality(build_starmap(weekends)) == "周末麦门人"


def test_summary_rounding():
    orders = [
        _order("R1", "薯条", "13.33", "2026-10-01 12:00:00"),
        _order("R2", "可乐", "11.11", "2026-10-02 12:00:00"),
    ]
    assert build_starmap(orders)["summary"]["totalAmount"] == 24.44


def test_demo_samples_personas():
    """四套演示数据必须产出四种不同人格（演示切换器的回归护栏）。"""
    import json
    import os

    base = os.path.join(os.path.dirname(__file__), "..", "samples")
    cases = {
        "demo_orders.json": "深夜麦门人",
        "demo_orders_breakfast.json": "早餐先行者",
        "demo_orders_dessert.json": "甜点星住民",
        "demo_orders_burger.json": "硬核堡星人",
    }
    seen = []
    for fname, expected in cases.items():
        with open(os.path.join(base, fname), encoding="utf-8") as f:
            orders = json.load(f)
        name = detect_personality(build_starmap(orders))
        assert name == expected, f"{fname} 应鉴出 {expected}，实际 {name}"
        seen.append(name)
    assert len(set(seen)) == 4, "四套演示必须覆盖四种不同人格"


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
