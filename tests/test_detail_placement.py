"""详情卡落点的静态守卫：CI 里没有浏览器，但"卡片压住刚点的那颗星"这类问题不能等人工发现。

这一轮之前，#detail 是钉死的（`left:50%; bottom:92px`，手机档改成 `top:24%`）——
按 1280×720 调的常数。实测：360×640 上它压住图例胶囊；桌面 10 颗星里盖住 2 颗、
手机盖住 4 颗、小屏 5 颗；点开的那颗星本身也常常就在卡片底下，等于"我点的是哪颗"看不见了。

现在落点由 placeDetail() 每次算：贴着那颗星、但那颗星和按钮区不许被盖。
E2E 会在三档屏幕 × 全部星点上真点一遍（30 次），但 E2E 不进 CI，
所以这里用纯文本审计守住同一个约定的骨架：

1. #detail 不许再钉死屏幕坐标，必须走 --dx/--dy；
2. DETAIL_HUD 障碍表必须包含按钮区（保存分享卡的主 CTA 不能被卡片压掉）；
3. 窄屏抽屉必须让人格卡"让位"，且收起时必须还原（让了位不还，人格卡就永久消失）。

三条审计都配证伪用例：改回旧写法，审计必须报错。
"""

from __future__ import annotations

import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATE = os.path.join(ROOT, "templates", "starmap.html")


def read_template() -> str:
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def audit_detail_anchor(html: str) -> list[str]:
    """详情卡不能把位置写死成屏幕坐标。"""
    m = re.search(r"#detail\s*\{([^}]*)\}", html)
    if not m:
        return ["找不到 #detail 的样式规则"]
    body = m.group(1)
    problems = []
    if re.search(r"left:\s*50%", body):
        problems.append("详情卡仍钉在 left:50%（宽屏靠右的星一被点就顶到边缘）")
    if re.search(r"bottom:\s*\d+px", body):
        problems.append("详情卡仍钉死 bottom（矮屏上会盖住刚点的那颗星）")
    if "--dx" not in body or "--dy" not in body:
        problems.append("详情卡没有走 --dx/--dy 变量定位（位置无法由代码算）")
    return problems


def detail_hud_ids(html: str) -> list[str]:
    m = re.search(r"var DETAIL_HUD = \[(.*?)\];", html, re.S)
    return re.findall(r'"([a-z-]+)"', m.group(1)) if m else []


def audit_detail_dispatch(html: str) -> list[str]:
    """落点必须由 placeDetail() 算，且障碍表里要有按钮区。"""
    problems = []
    if "function placeDetail(" not in html:
        problems.append("没有 placeDetail()：落点仍是写死的")
    if not re.search(r"placeDetail\(s\);", html):
        problems.append("showDetail() 没有调用 placeDetail()（算出来也没人用）")
    ids = detail_hud_ids(html)
    if not ids:
        problems.append("找不到 DETAIL_HUD 障碍表")
    else:
        for need in ("actions", "legend", "persona", "title"):
            if need not in ids:
                problems.append(f"DETAIL_HUD 缺 {need}：卡片会压住它")
    return problems


def audit_persona_yield(html: str) -> list[str]:
    """窄屏抽屉占位时人格卡让位，收起时必须还原。"""
    problems = []
    if not re.search(r"if \(W < 640\)", html):
        problems.append("没有窄屏分支：手机上 183px 的卡片在星群带里无处可放")
    if 'personaEl.classList.add("yield")' not in html:
        problems.append("窄屏抽屉没有让人格卡让位（两张不透明卡片会互相切边）")
    if not re.search(r"#persona\.yield\s*\{", html):
        problems.append("缺少 #persona.yield 样式")
    hide = re.search(r"function hideDetail\(\) \{(.*?)\n  \}", html, re.S)
    if not hide:
        problems.append("找不到 hideDetail()：收起路径不统一")
    elif 'personaEl.classList.remove("yield")' not in hide.group(1):
        problems.append("收起详情时没有让人格卡回来（让了位不还 = 永久消失）")
    return problems


def audit(html: str) -> list[str]:
    return audit_detail_anchor(html) + audit_detail_dispatch(html) + audit_persona_yield(html)


def test_template_passes_detail_placement_guards():
    problems = audit(read_template())
    assert problems == [], "详情卡落点检查未通过:\n" + "\n".join(problems)


def test_audit_catches_hardcoded_anchor():
    """证伪：把落点改回旧的 fixed 坐标，审计必须报错。"""
    html = read_template()
    mutated = html.replace(
        "#detail { left: 0; top: 0; --dx: 0px; --dy: 0px;",
        "#detail { left: 50%; bottom: 92px;",
    )
    assert mutated != html, "证伪用例没生效：模板里找不到 #detail 的定位声明"
    problems = audit_detail_anchor(mutated)
    assert any("left:50%" in p for p in problems)
    assert any("钉死 bottom" in p for p in problems)


def test_audit_catches_missing_actions_obstacle():
    """证伪：障碍表里去掉按钮区，审计必须报错（主 CTA 被压就点不着了）。"""
    html = read_template()
    marker = '"legend", "persona", "actions", "footer"'
    assert marker in html, "模板里找不到 DETAIL_HUD 的尾部条目"
    mutated = html.replace(marker, '"legend", "persona", "footer"')
    problems = audit_detail_dispatch(mutated)
    assert any("actions" in p for p in problems)


def test_audit_catches_unrestored_persona():
    """证伪：收起时不还原人格卡，审计必须报错。"""
    html = read_template()
    marker = '    personaEl.classList.remove("yield");\n'
    assert marker in html, "模板里找不到人格卡的还原语句"
    mutated = html.replace(marker, "")
    problems = audit_persona_yield(mutated)
    assert any("永久消失" in p for p in problems)
