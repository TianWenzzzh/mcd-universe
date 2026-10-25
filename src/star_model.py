"""星图数据模型：麦当劳订单 -> 个人星图 + 麦门人格。

核心映射：
  每一笔订单 = 一颗星
  颜色 = 订单主餐品品类（汉堡/小食/甜品/饮品/早餐）
  星等 = 消费频次与金额（1~5）
  时间轴 = 下单时间（createTime）

0 单账号输出 "nebula"（星云）状态，不是空报错——新账号也是有效用户。
"""

from __future__ import annotations

from datetime import datetime

# 品类规则：(品类, 色, 关键词)。自上而下首个命中生效——早餐关键词更具体，必须置于汉堡之前。
CATEGORY_RULES = [
    ("早餐", "#BA7517", ["早餐", "麦满分", "猪柳", "烟肉", "火腿扒", "脆薯饼", "滑蛋"]),
    ("汉堡", "#E24B4A", ["汉堡", "巨无霸", "腿堡", "板烧", "麦香鱼", "安格斯", "培根", "双层"]),
    ("甜品", "#D4537E", ["新地", "冰淇淋", "圆筒", "甜筒", "派", "蛋挞", "蛋糕", "巧克力", "可可"]),
    ("小食", "#EF9F27", ["薯条", "麦乐鸡", "鸡翅", "玉米杯", "洋葱圈", "鸡块", "鸡排", "盐酥鸡"]),
    ("饮品", "#378ADD", ["可乐", "雪碧", "咖啡", "拿铁", "美式", "茶", "果汁", "奶昔", "冰饮", "雪冰"]),
]
CATEGORY_NAMES = ["汉堡", "早餐", "甜品", "小食", "饮品"]
FALLBACK_CATEGORY = "小食"


def categorize(product_name: str) -> str:
    """餐品名 -> 品类。规则自上而下首个命中。"""
    for cat, _color, keywords in CATEGORY_RULES:
        if any(k in product_name for k in keywords):
            return cat
    return FALLBACK_CATEGORY


def category_color(cat: str) -> str:
    for c, color, _kw in CATEGORY_RULES:
        if c == cat:
            return color
    return "#888780"


def _order_main_product(order: dict) -> str | None:
    products = order.get("orderProductList") or []
    if not products:
        return None
    # 主餐品 = 数量最多的第一个商品
    main = max(products, key=lambda p: int(p.get("quantity") or 0))
    return main.get("productName") or None


def _parse_time(create_time: str | None) -> datetime | None:
    if not create_time:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(create_time, fmt)
        except ValueError:
            continue
    return None


def _magnitude(amount: object, qty: int) -> int:
    """星等 1~5：金额为主，数量加成。"""
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        amt = 0.0
    base = 1 if amt < 20 else 2 if amt < 40 else 3 if amt < 70 else 4 if amt < 120 else 5
    return min(5, base + (1 if qty >= 4 else 0))


def build_starmap(orders: list) -> dict:
    """订单列表 -> 星图数据。0 单返回 nebula 状态。"""
    if not orders:
        return {"status": "nebula", "stars": [], "summary": {"orderCount": 0, "totalAmount": 0.0}}

    stars = []
    total = 0.0
    for i, order in enumerate(orders):
        name = _order_main_product(order)
        cat = categorize(name) if name else FALLBACK_CATEGORY
        qty = sum(int(p.get("quantity") or 0) for p in (order.get("orderProductList") or []))
        try:
            amount = float(order.get("realTotalAmount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        total += amount
        stars.append(
            {
                "id": order.get("orderId") or f"star-{i}",
                "category": cat,
                "color": category_color(cat),
                "magnitude": _magnitude(order.get("realTotalAmount"), qty),
                "time": order.get("createTime"),
                "dt": _parse_time(order.get("createTime")),
                "product": name,
                "store": order.get("storeName"),
                "amount": amount,
                "quantity": qty,
            }
        )

    stars.sort(key=lambda s: s["dt"] or datetime.min)
    return {
        "status": "galaxy",
        "stars": stars,
        "summary": {"orderCount": len(stars), "totalAmount": round(total, 2)},
    }


# 麦门人格图鉴：单一数据源。detect_personality 只返回名字，文案从这里取——图鉴与鉴定永不漂移。
PERSONAS = {
    "深夜麦门人": "城市的深夜，总有一盏麦麦的灯为你亮着。你是夜色里最忠实的那颗星。",
    "早餐先行者": "一日之计在于晨，你的早晨从麦满分开始。整片宇宙都醒得比你晚。",
    "甜点星住民": "你的宇宙有一股甜味儿。生活再苦，你也要给自己留一颗糖。",
    "周末麦门人": "工作日属于世界，周末属于麦麦。你的星星总在休息日最闪亮。",
    "硬核堡星人": "大道至简，堡以载道。你的胃有态度，你的星有分量。",
    "麦门探索者": "菜单是你的星图，你从不重复同一颗星。探索是你的浪漫。",
    "麦门旅人": "不困于一种口味，不忠于一家门店。你路过麦门，麦门记住你。",
}


def detect_personality(starmap: dict) -> str:
    """麦门人格鉴定。全部正面向；任何输入都有结果（默认：麦门旅人）。"""
    stars = starmap.get("stars") or []
    if not stars:
        return "麦门旅人"

    from collections import Counter

    cats = Counter(s["category"] for s in stars)
    total = len(stars)
    hours = [s["dt"].hour for s in stars if s["dt"]]
    night = sum(1 for h in hours if h >= 22 or h < 3)  # 深夜：22 点至次日 3 点前（含 2 点档，实测凌晨订单在此区间）
    morning = sum(1 for h in hours if 5 <= h < 10)
    weekend = sum(1 for s in stars if s["dt"] and s["dt"].weekday() >= 5)
    top_cat, top_n = cats.most_common(1)[0]

    if night >= 2 and night / max(total, 1) >= 0.3:
        return "深夜麦门人"
    if morning >= 2 and morning / max(total, 1) >= 0.4:
        return "早餐先行者"
    if weekend >= 2 and weekend / max(total, 1) >= 0.5:
        return "周末麦门人"
    if top_cat == "甜品" and top_n / total >= 0.4:
        return "甜点星住民"
    if top_cat == "汉堡":
        return "硬核堡星人"
    if len({s["product"] for s in stars}) >= max(5, total * 0.6):
        return "麦门探索者"
    return "麦门旅人"
