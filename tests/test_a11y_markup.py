"""无障碍标记的静态守卫：把"读屏/键盘用户能不能用"变成可断言的规则。

为什么要有这一层：`scripts/a11y_audit.mjs` 能查出真问题，但它要浏览器、要起服务、
跑一次几十秒，进不了 `pytest` 的快循环。这里用纯标准库把最容易回退的那几条固定住
（缺标签、假链接、模态没名字、反馈不在 live region、aria 指向不存在的 id）——
这些一旦被改回去，代码看上去仍然"正常"，只有读屏用户会撞上。

每条规则都配一个"证伪"用例：喂一段故意写坏的 HTML，断言检查器真的报错。
一个永远返回 [] 的检查器也能让主用例变绿，所以必须先证明它会红。
"""

import os
import unittest
from html.parser import HTMLParser

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "starmap.html")

VOID = {"br", "img", "input", "meta", "link", "hr", "source", "area", "col", "embed"}


class _Collector(HTMLParser):
    """收集标签、属性、id 与可访问名字的原始材料。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []  # [(tag, attrs_dict)]
        self.ids = []
        self.labels_for = []
        self.stack = []  # 用于判断 textarea 是否被 label 包着
        self._capture = []  # 正在收集文字的节点 id
        self.text_by_parent = {}

    def handle_starttag(self, tag, attrs):
        d = {k: (v if v is not None else "") for k, v in attrs}
        self.tags.append((tag, d))
        if d.get("id"):
            self.ids.append(d["id"])
        if tag == "label" and d.get("for"):
            self.labels_for.append(d["for"])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack:
                if self.stack.pop() == tag:
                    break


def parse(html: str) -> _Collector:
    c = _Collector()
    c.feed(html)
    c.close()
    return c


def _by_id(c: _Collector, id_: str):
    for tag, d in c.tags:
        if d.get("id") == id_:
            return tag, d
    return None, None


def audit(html: str) -> list:
    """返回问题列表（字符串）。空列表 = 通过。"""
    c = parse(html)
    problems = []
    ids = set(c.ids)

    # 1. 重复 id：aria-labelledby 会指到先出现的那个，后面的失去名字
    seen = set()
    for i in c.ids:
        if i in seen:
            problems.append(f"重复 id：{i}")
        seen.add(i)

    # 2. 所有 aria-* 的 id 引用都必须真的存在
    for tag, d in c.tags:
        for attr in ("aria-labelledby", "aria-describedby", "aria-controls", "aria-owns"):
            v = d.get(attr)
            if not v:
                continue
            for ref in v.split():
                if ref not in ids:
                    problems.append(f"<{tag}{'#' + d['id'] if d.get('id') else ''}> 的 {attr} 指向不存在的 id：{ref}")

    # 3. 表单控件必须有名字（aria-label / aria-labelledby / label[for] / 外层 label）
    labelled = set(c.labels_for)
    for tag, d in c.tags:
        if tag not in ("textarea", "select", "input"):
            continue
        if d.get("type") in ("hidden", "submit", "button"):
            continue
        name = d.get("aria-label") or d.get("aria-labelledby")
        if name:
            continue
        if d.get("id") and d["id"] in labelled:
            continue
        problems.append(f"<{tag}#{d.get('id', '?')}> 没有可访问名（placeholder 不算）")

    # 4. 不许有 href="#" 的伪链接
    for tag, d in c.tags:
        if tag == "a" and d.get("href") == "#":
            problems.append(f'<a#{d.get("id", "?")}> 用 href="#" 冒充按钮')

    # 5. 模态框必须有名字，且名字来自可见标题（aria-labelledby 而非手写 aria-label）
    for _tag, d in c.tags:
        if d.get("role") != "dialog":
            continue
        who = "#" + d.get("id", "?")
        if not (d.get("aria-label") or d.get("aria-labelledby")):
            problems.append(f"{who} 是 role=dialog 但没有可访问名")
        if d.get("aria-label") and d.get("aria-labelledby"):
            problems.append(f"{who} 同时写了 aria-label 与 aria-labelledby")
        if not d.get("aria-modal"):
            problems.append(f"{who} 少了 aria-modal（读屏不会把背景当惰性内容）")

    # 6. 操作反馈必须在 live region 里
    for id_, must in (("toast", ("role", "status")), ("import-err", ("role", "alert"))):
        tag, d = _by_id(c, id_)
        if tag is None:
            problems.append(f"缺少 #{id_}")
            continue
        attr, val = must
        if d.get(attr) != val and not d.get("aria-live"):
            problems.append(f"#{id_} 不在 live region 里（读屏听不到这条反馈）")

    # 7. 星图画布：要收键盘，就不能声明成静态图
    tag, d = _by_id(c, "sky")
    if tag is None:
        problems.append("缺少 #sky 画布")
    else:
        if d.get("role") == "img" and d.get("tabindex") is not None:
            problems.append("#sky 是 role=img 却可聚焦：读屏进图片模式，方向键收不到")
        if d.get("tabindex") is None:
            problems.append("#sky 不可聚焦：键盘用户无法逐颗浏览")
        if not d.get("aria-describedby"):
            problems.append("#sky 没有 aria-describedby：键位说明无处可放")

    return problems


def audit_file(path=TEMPLATE) -> list:
    with open(path, encoding="utf-8") as f:
        return audit(f.read())


class TestTemplateA11y(unittest.TestCase):
    def test_template_clean(self):
        problems = audit_file()
        self.assertEqual(problems, [], "模板无障碍标记有问题：\n" + "\n".join(problems))

    def test_no_duplicate_ids(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            c = parse(f.read())
        self.assertEqual(len(c.ids), len(set(c.ids)))

    def test_form_control_has_label_element(self):
        # 光有 aria-label 还不够直观；这条确认模板里真的存在 label[for] 的写法
        with open(TEMPLATE, encoding="utf-8") as f:
            html = f.read()
        self.assertIn('label class="sr-only" for="import-text"', html)


class TestFalsification(unittest.TestCase):
    """每条规则都要能真的报错，否则主用例绿得毫无意义。"""

    def test_catches_missing_field_label(self):
        html = '<textarea id="t"></textarea>'
        self.assertTrue(any("没有可访问名" in p for p in audit(html)))

    def test_catches_fake_link(self):
        self.assertTrue(any("href" in p for p in audit('<a href="#" id="x">y</a>')))

    def test_catches_dialog_without_name(self):
        self.assertTrue(any("没有可访问名" in p for p in audit('<div role="dialog" aria-modal="true"></div>')))

    def test_catches_missing_modal(self):
        html = '<div role="dialog" aria-label="x"></div>'
        self.assertTrue(any("aria-modal" in p for p in audit(html)))

    def test_catches_toast_without_live(self):
        html = '<div id="toast"></div><p id="import-err" role="alert"></p>'
        self.assertTrue(any("toast" in p for p in audit(html)))

    def test_catches_img_role_on_focusable_canvas(self):
        html = '<canvas id="sky" role="img" tabindex="0"></canvas>'
        self.assertTrue(any("role=img" in p for p in audit(html)))

    def test_catches_dangling_aria_reference(self):
        html = '<canvas id="sky" role="application" tabindex="0" aria-describedby="nope"></canvas>'
        self.assertTrue(any("不存在的 id" in p for p in audit(html)))

    def test_catches_duplicate_id(self):
        html = '<div id="a"></div><div id="a"></div>'
        self.assertTrue(any("重复 id" in p for p in audit(html)))


if __name__ == "__main__":
    unittest.main()
