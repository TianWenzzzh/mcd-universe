"""首屏信息层级与成就列表的静态守卫。

这一轮的三个产品决策如果只靠截图验收，下一次改版很容易被无意推翻：
1. 「粘贴订单，生成星图」必须是首屏唯一的高对比主 CTA；
2. 低频动作收进「更多」，底部主栏只留成就/导出/更多；
3. 成就列表必须存在「汉堡王」，粒子目标必须等距覆盖整段文字。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = (ROOT / "templates" / "starmap.html").read_text(encoding="utf-8")
ACTIONS = re.search(r'<div id="actions">(.*?)</div>', TPL, re.S)
ACH = re.search(r"function computeAchievements\(\) (\{.*?)\n  \}", TPL, re.S)
PARTICLES = re.search(r"function buildParticles\(\) (\{.*?)\n  \}", TPL, re.S)


def test_primary_cta_is_the_first_main_action() -> None:
    cta = TPL.index('id="import-open"')
    sample = TPL.index('id="sample-select"')
    assert cta < sample, "样例选择器跑到主 CTA 前面了"
    assert "粘贴订单，生成星图" in TPL[cta : cta + 300]


def test_bottom_bar_has_only_three_actions() -> None:
    assert ACTIONS, "找不到 #actions"
    ids = re.findall(r'id="(btn-[^"]+)"', ACTIONS.group(1))
    assert ids == ["btn-ach", "btn-save", "btn-more"], ids


def test_personality_dex_is_replaced_by_achievements() -> None:
    assert "人格图鉴" not in TPL, "人格图鉴文案还在，用户会看到旧入口"
    assert 'id="btn-dex"' not in TPL
    assert 'id="ach-panel"' in TPL
    assert "汉堡王" in TPL
    assert "ach-item" in TPL


def test_achievement_data_has_progress_and_burger_king() -> None:
    assert ACH, "找不到 computeAchievements"
    body = ACH.group(1)
    assert '"汉堡王"' in body
    assert body.count("cap(") >= 8, "成就定义应当带完成比例"
    assert "progress(" in body


def test_particle_targets_spread_over_the_whole_text() -> None:
    assert PARTICLES, "找不到 buildParticles"
    body = PARTICLES.group(1)
    assert "Math.floor(i * pts.length / Math.max(1, n))" in body, "粒子目标又退回取采样点前缀"
    assert "pts[i % pts.length]" not in body, "取模前缀会让文字只剩上半截"
