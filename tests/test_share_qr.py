"""分享卡二维码的静态守卫：卡上的码必须指向「打开这张卡的站点」，且留足静区。

为什么单独守这两条：
1. 卡里的码是**预生成 PNG**，写死在模板里。它指向哪里，光看代码看不出来 ——
   扫码的人会去哪，只有解出那张图才知道。同一份 HTML 服务两套域名（Pages 与国内镜像），
   码写死一条就等于所有卡都扫回同一处：国内实测镜像首字节 0.25s、Pages 9.9~13.1s（三次里两次 5s 就断）。
2. 静区不足时码「看着还在」，但缩到信息流那一屏宽就解不出来。旧写法给 8px（2.1 个模块），
   规范要 4 个；这是本轮实拍的回归点，靠肉眼永远看不出来。

这里用「按声明的 url 重新编码一遍，字节必须完全相同」来钉住 PNG 与 URL 的绑定 ——
不需要解码器，也不会因为重拍而漂移。占位图和 URL 各自改动都会红。
"""

from __future__ import annotations

import base64
import importlib.util
import math
import os
import re
import sys
from pathlib import Path

import pytest

qrcode = pytest.importorskip("qrcode", reason="二维码守卫需要开发依赖 qrcode")

ROOT = Path(__file__).resolve().parent.parent
TPL = (ROOT / "templates" / "starmap.html").read_text(encoding="utf-8")


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


qrgen = _load("make_qr", "scripts/make_qr.py")

VARIANT_IDS = ["pages", "mirror"]

VARIANTS = re.findall(
    r'var (QR_PAGES|QR_MIRROR) = \{ uri: "data:image/png;base64,([^"]+)", modules: (\d+), url: "([^"]+)" \};',
    TPL,
)
CARD_SIZES = sorted({int(m) for m in re.findall(r"qr: \{ size: (\d+),", TPL)})
QR_QUIET = int(re.search(r"var QR_QUIET = (\d+);", TPL).group(1))


def test_both_site_variants_are_embedded() -> None:
    names = [v[0] for v in VARIANTS]
    assert names == ["QR_PAGES", "QR_MIRROR"], f"二维码分支应为 Pages + 镜像两条，实际 {names}"
    blobs = [v[1] for v in VARIANTS]
    assert blobs[0] != blobs[1], "两个站点内嵌了同一张码"


@pytest.mark.parametrize("name,blob,modules,url", VARIANTS, ids=VARIANT_IDS)
def test_embedded_png_really_encodes_its_url(name: str, blob: str, modules: str, url: str, tmp_path: Path) -> None:
    """把声明的 url 重新编码一遍，字节必须与内嵌的 PNG 完全一致。"""
    png = base64.b64decode(blob)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", f"{name} 不是 PNG"
    # IHDR：16..20 宽、20..24 高、24 位深、25 色彩类型。模块边长 = 宽 / 模块数。
    side = int.from_bytes(png[16:20], "big")
    assert side == int.from_bytes(png[20:24], "big"), f"{name} 不是正方形"
    assert png[24] == 8 and png[25] == 0, f"{name} 不是 8bit 灰度"
    per_module = side / int(modules)
    assert per_module == qrgen.MODULE_PX, f"{name}: 模块边长 {per_module}px，写图脚本用的是 {qrgen.MODULE_PX}px"

    qr = qrcode.QRCode(border=0, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    assert len(matrix) == int(modules), (
        f"{name}: 声明 {modules} 个模块，按 url 实编是 {len(matrix)} 个 —— URL 与图不是同一版"
    )

    out = tmp_path / f"{name}.png"
    qrgen.write_png(str(out), matrix)
    assert out.read_bytes() == png, f"{name} 的图和它声明的 url 不是同一张码 —— 卡上印的地址会把人送到别处"


@pytest.mark.parametrize("name,blob,modules,url", VARIANTS, ids=VARIANT_IDS)
def test_variant_points_at_the_host_it_serves(name: str, blob: str, modules: str, url: str) -> None:
    if name == "QR_PAGES":
        assert "github.io" in url, "Pages 版的码必须指向 Pages"
    else:
        assert "github.io" not in url, "镜像版的码不能指回 Pages —— 国内扫码会等十几秒"
        assert url.rstrip("/").endswith("/mcd/demo"), f"镜像码的目标路径不对：{url}"


def test_selector_picks_by_serving_host() -> None:
    """选择逻辑必须认站点，且非 github.io 一律走镜像（本地与镜像都算）。"""
    line = re.search(r"var QR = [^\r\n]+", TPL)
    assert line, "找不到二维码选择逻辑"
    src = line.group(0)
    assert r"github\.io" in src, "选择逻辑没有看站点"
    assert "? QR_PAGES" in src and ": QR_MIRROR" in src, "github.io 应选 Pages，其余选镜像"


def test_mirror_build_still_binds_the_qr_it_actually_draws(tmp_path: Path) -> None:
    """镜像打包会把 Pages 站址改写成镜像口径 —— 改写之后，镜像页真正会画的那张码必须仍配套。

    镜像页的 hostname 不是 github.io，走 QR_MIRROR；那条 url 不含 Pages 站址，改写碰不到它。
    这条守的是"生产上真会跑到的那条分支"，而不是源文件里好看的那条。
    """
    pytest.importorskip("paramiko", reason="镜像同步脚本依赖 paramiko")
    mirror = _load("sync_mirror", "deploy/sync_mirror.py")
    rewritten = mirror.rewrite_hosts(TPL)

    hit = re.search(
        r'var QR_MIRROR = \{ uri: "data:image/png;base64,([^"]+)", modules: (\d+), url: "([^"]+)" \};',
        rewritten,
    )
    assert hit, "改写后找不到镜像版二维码"
    blob, modules, url = hit.groups()
    assert url == next(v[3] for v in VARIANTS if v[0] == "QR_MIRROR"), "镜像页的码在打包时被改写了"

    qr = qrcode.QRCode(border=0, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    out = tmp_path / "mirror.png"
    qrgen.write_png(str(out), qr.get_matrix())
    assert out.read_bytes() == base64.b64decode(blob), "镜像页画出来的码与它声明的地址不是同一张"


def test_card_sizes_are_known() -> None:
    assert CARD_SIZES == [132, 140], f"卡上的二维码尺寸变了（{CARD_SIZES}），静区结论要重新算"


def _js_inset(size: int, modules: int) -> int:
    """求值模板里那段真实的 qrInset（不是照着它再写一遍）。

    照写一遍的守卫只能证明"我的公式算得对"，改坏了 JS 它照样绿 —— 这里把表达式抠出来算。
    """
    body = re.search(r"function qrInset\(size\) \{\s*return ([^;]+);", TPL)
    assert body, "找不到 qrInset 的实现"
    expr = body.group(1)
    expr = re.sub(r"Math\.(ceil|round|max|abs)", r"\1", expr)
    expr = expr.replace("QR.modules", str(modules))
    expr = re.sub(r"\bQR_QUIET\b", str(QR_QUIET), expr)
    expr = re.sub(r"\bsize\b", str(size), expr)
    return int(eval(expr, {"__builtins__": {}}, {"ceil": math.ceil, "round": round, "max": max, "abs": abs}))


@pytest.mark.parametrize("size", CARD_SIZES)
@pytest.mark.parametrize("name,blob,modules,url", VARIANTS, ids=VARIANT_IDS)
def test_quiet_zone_meets_the_spec(size: int, name: str, blob: str, modules: str, url: str) -> None:
    """白框内缩就是静区：i >= 4 * (size-2i)/modules 才够 4 个模块。"""
    m = int(modules)
    inset = _js_inset(size, m)
    code = size - inset * 2
    per_module = code / m
    quiet = inset / per_module
    assert quiet >= QR_QUIET, f"{name}@{size}px 静区只有 {quiet:.2f} 个模块（要 {QR_QUIET}）"
    assert inset > 12, f"{name}@{size}px 静区 {inset}px 会被 12px 圆角啃进码区"
    assert per_module >= 3, f"{name}@{size}px 每个模块只剩 {per_module:.2f}px，缩小就糊"
    assert code > 0
