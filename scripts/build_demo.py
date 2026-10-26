"""重建 demo/ 下的四个演示页（模板 + 匿名化样本）。

四个演示页（深夜 / 早餐 / 甜点 / 汉堡）是 `templates/starmap.html` 注入不同样本数据生成的。
以前靠手敲四条命令，模板一改就容易漏掉某几页 —— 这类"产物与源码不同步"正是死链、
旧文案截图反复出现的根源。这里把四条命令固定下来，并提供 --check 供 CI 守卫。

用法：
    python scripts/build_demo.py            # 重建全部页面
    python scripts/build_demo.py --check    # 只检查是否同步（CI 用，不同步则 exit 1）
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "scripts" / "generate_report.py"

# 页面 -> 样本：顺序即导航顺序
PAGES: list[tuple[str, str]] = [
    ("samples/demo_orders.json", "demo/index.html"),
    ("samples/demo_orders_breakfast.json", "demo/breakfast.html"),
    ("samples/demo_orders_dessert.json", "demo/dessert.html"),
    ("samples/demo_orders_burger.json", "demo/burger.html"),
]


def differs(fresh: str, current: str) -> bool:
    """产物与源码是否不同步。

    换行统一成 LF 再比：Windows 上 CRLF/LF 混用不该被当成"不同步"，
    但任何一个字符的实质差异（哪怕只改了一行文案）都必须判为不同步。
    """
    return fresh.replace("\r\n", "\n") != current.replace("\r\n", "\n")


def build_one(sample: str, out: Path) -> None:
    """调用主管线生成单页（保持单一数据源，不在本脚本里重复注入逻辑）。"""
    import subprocess

    subprocess.run(
        [sys.executable, str(GENERATOR), "--demo", str(ROOT / sample), "-o", str(out)],
        check=True,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="重建 demo/ 演示页")
    ap.add_argument("--check", action="store_true", help="只校验产物是否与模板同步")
    args = ap.parse_args()

    stale: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for sample, page in PAGES:
            target = ROOT / page
            if args.check:
                tmp_out = Path(tmp) / Path(page).name
                build_one(sample, tmp_out)
                # 统一按 UTF-8 文本比较，避免 Windows CRLF 误报
                fresh = tmp_out.read_text(encoding="utf-8")
                current = target.read_text(encoding="utf-8")
                if differs(fresh, current):
                    stale.append(page)
                else:
                    print(f"OK   {page}")
            else:
                build_one(sample, target)
                print(f"built {page}")

    if stale:
        print("\n以下页面与模板不同步，请运行 python scripts/build_demo.py 重建：")
        for page in stale:
            print(f"  - {page}")
        return 1
    if args.check:
        print("\n四个演示页均与模板同步。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
