"""交付链路的静态守卫：CI 里没有浏览器，但"分享卡存不下来"这类问题不能等到人工发现。

E2E 已经在真实浏览器里验过交付路径（微信 / iOS / 普通浏览器三种容器），但 E2E 不进 CI
（要下载 Chromium + 起本地服务）。这里用纯文本审计兜住最容易退化的三条结构性约定：

1. 三层浮层（首访引导 / 分享卡预览 / 导出面板）都必须是真对话框：role + aria-modal；
2. 交付路径的判据必须包含微信（MicroMessenger），不能退回"只判 iOS"；
3. 首访引导的延时要按 prefers-reduced-motion 分档，不能写成一个固定常数。

三条审计函数都单独可测，并且各配一条**证伪**用例 —— 把代码改回旧写法，审计必须报错。
"""

from __future__ import annotations

import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATE = os.path.join(ROOT, "templates", "starmap.html")


def read_template() -> str:
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def audit_dialog_roles(html: str) -> list[str]:
    """三个全屏浮层是否都声明了对话框语义。"""
    problems = []
    for el_id, label in (("onboard", "首访引导"), ("img-preview", "分享卡预览"), ("export-panel", "导出面板")):
        m = re.search(rf'<div id="{re.escape(el_id)}"[^>]*>', html)
        if not m:
            problems.append(f"找不到 {label} 容器 (#{el_id})")
            continue
        tag = m.group(0)
        if 'role="dialog"' not in tag:
            problems.append(f"{label} 缺 role=dialog")
        if 'aria-modal="true"' not in tag:
            problems.append(f"{label} 缺 aria-modal=true")
        # 名字可以来自 aria-label，也可以来自可见标题的 aria-labelledby（后者更好：
        # 读屏念的和眼睛看到的必须是同一句话）。用了 labelledby 就得真的指得到。
        if "aria-label" in tag:
            pass
        elif "aria-labelledby" in tag:
            ref = re.search(r'aria-labelledby="([^"]+)"', tag)
            for rid in ref.group(1).split() if ref else []:
                if f'id="{rid}"' not in html:
                    problems.append(f"{label} 的 aria-labelledby 指向不存在的 id：{rid}")
        else:
            problems.append(f"{label} 缺可访问名（aria-label 或 aria-labelledby）")
    return problems


def audit_save_mode(html: str) -> list[str]:
    """交付路径的判据必须是"容器能不能下载"，不是"是不是 iPhone"。"""
    problems = []
    if "MicroMessenger" not in html:
        problems.append("交付路径没有识别微信内置浏览器（微信不实现 a[download]，点了没反应）")
    if "SAVE_MODE" not in html:
        problems.append("没有统一的交付路径判定（SAVE_MODE）")
    # 判据里必须同时出现微信与 iOS 两个条件
    if not re.search(r"SAVE_MODE\s*=\s*IS_WECHAT\s*\|\|\s*IS_IOS", html):
        problems.append("SAVE_MODE 未同时考虑微信与 iOS")
    # 预览路径不许再套一句"已导出"
    if re.search(r'toast\(\s*"已导出「"\s*\+\s*th\.name', html):
        problems.append("预览路径仍无条件提示「已导出」（文件其实还在页面里，用户没长按就什么都没存）")
    return problems


def audit_onboard_delay(html: str) -> list[str]:
    """首访引导的延时要跟着 reduced-motion 走。"""
    m = re.search(r"setTimeout\(function \(\) \{\s*if \(!onboardDismissed\) obShow\(true\);\s*\},\s*([^)]+)\)", html)
    if not m:
        return ["找不到首访引导的定时器（文案与动画时序都依赖它）"]
    delay = m.group(1)
    if "REDUCED" not in delay:
        return [f"引导延时写成了固定值（{delay.strip()}）：减少动效的用户没有动画可等，会对着静态星图白等"]
    return []


def audit(html: str) -> list[str]:
    return audit_dialog_roles(html) + audit_save_mode(html) + audit_onboard_delay(html)


def test_template_passes_all_delivery_guards():
    problems = audit(read_template())
    assert problems == [], "模板交付链路检查未通过:\n" + "\n".join(problems)


def test_audit_catches_missing_dialog_role():
    """证伪：把引导层的 role/aria-modal 拿掉，审计必须报出来。"""
    html = read_template()
    mutated = html.replace(
        '<div id="onboard" role="dialog" aria-modal="true" aria-labelledby="onboard-title">', '<div id="onboard">'
    )
    assert mutated != html, "证伪用例没生效：模板里找不到引导层的 role 声明"
    problems = audit_dialog_roles(mutated)
    assert any("首访引导 缺 role=dialog" in p for p in problems)
    assert any("aria-modal" in p for p in problems)


def test_audit_catches_ios_only_save_mode():
    """证伪：退回"只判 iOS"的老写法，审计必须报错。"""
    html = read_template()
    mutated = html.replace(
        'var SAVE_MODE = IS_WECHAT || IS_IOS ? "preview" : "download";',
        'var SAVE_MODE = IS_IOS ? "preview" : "download";',
    )
    assert mutated != html, "证伪用例没生效：模板里找不到 SAVE_MODE 判定"
    problems = audit_save_mode(mutated)
    assert any("未同时考虑微信与 iOS" in p for p in problems)


def test_audit_catches_fixed_onboard_delay():
    """证伪：把延时写回固定 5200ms，审计必须报错。"""
    html = read_template()
    mutated = html.replace("}, REDUCED ? 800 : 5200);", "}, 5200);")
    assert mutated != html, "证伪用例没生效：模板里找不到引导延时"
    problems = audit_onboard_delay(mutated)
    assert problems and "固定值" in problems[0]


def test_audit_catches_unconditional_export_toast():
    """证伪：预览路径若仍写死"已导出"，审计必须报错。"""
    html = read_template()
    marker = 'toast(mode === "preview"'
    assert marker in html, "模板里找不到按交付路径分流的提示"
    mutated = html.replace(marker, 'toast("已导出「" + th.name + "」分享卡" || (mode === "preview"')
    problems = audit_save_mode(mutated)
    assert any("已导出" in p for p in problems)
