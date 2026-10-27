#!/usr/bin/env python3
"""把 demo/ 与 docs/ 同步到国内镜像服务器（免密，走专用 SSH 密钥）。

用法：
    python deploy/sync_mirror.py            # 同步并自检
    python deploy/sync_mirror.py --check    # 只自检，不传输

环境变量（都有默认值）：
    MCD_MIRROR_HOST  默认 47.114.38.125
    MCD_MIRROR_USER  默认 root
    MCD_MIRROR_KEY   默认 ~/.ssh/mcuniverse_deploy
    MCD_MIRROR_PATH  默认 /opt/caddy/config/mcd-site

依赖：paramiko（开发依赖，运行时零依赖不涉及）。
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tarfile

import paramiko

HOST = os.environ.get("MCD_MIRROR_HOST", "47.114.38.125")
USER = os.environ.get("MCD_MIRROR_USER", "root")
KEY = os.path.expanduser(os.environ.get("MCD_MIRROR_KEY", "~/.ssh/mcuniverse_deploy"))
REMOTE_DIR = os.environ.get("MCD_MIRROR_PATH", "/opt/caddy/config/mcd-site")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 镜像的对外前缀。页面在这个前缀下被打开，页面里所有"绝对地址"就应该说这个前缀。
MIRROR_BASE = os.environ.get("MCD_MIRROR_BASE", f"http://{HOST}/mcd/")

# 源文件里的绝对站址（GitHub Pages）。与 check_meta.SITE 同一份定义，别在这里再抄一遍。
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from check_meta import SITE  # noqa: E402

# docs/assets 里"页面真的会去取"的单列文件：体积小、少一张就少一块功能。
# og-card.jpg 是说明页与演示页的 og:image —— 漏了它，镜像链接转进微信就是一张灰卡
# （线上实测 404，白名单只认 *-web.jpg 的那一版一直在悄悄漏传）。
REFERENCED_ASSETS = ("demo-poster.jpg", "og-card.jpg")


def rewrite_hosts(text: str, base: str = MIRROR_BASE) -> str:
    """把页面里的绝对站址换成本站前缀。

    og:image / og:url 必须是绝对地址（抓取器不认相对路径），而同一份 HTML 要同时服务
    Pages 与镜像两套域名。源文件里只能写一个，于是按目标站点在同步这一步重写。

    不重写的后果实测过：镜像页声明 og:image 在 github.io，抓取器为了取一张 72KB 的图
    要多跨一站；那台主机在国内时好时坏，卡片就时有时无。（图本身镜像上一直有，
    0.23s 就能取到。）
    """
    return text.replace(SITE, base)


def _keep(arc: str) -> bool:
    """镜像只收 Web 优化版（*-web.jpg / *-web.gif / .mp4）与页面引用的小图。

    原图（2 倍 PNG、未压缩 GIF）只用于投稿材料上传，不必占用镜像带宽。
    """
    if arc.endswith("/"):
        return True
    if "/assets/" in arc:
        return arc.endswith(("-web.jpg", "-web.gif", ".mp4", *REFERENCED_ASSETS))
    return True


def _filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """tarfile 的 filter 回调（保留旧签名，tests 里直接调它验白名单）。"""
    return tarinfo if _keep(tarinfo.name.replace("\\", "/")) else None


def build_tar() -> bytes:
    """把 demo/ 与 docs/ 打成 tar.gz（内存中完成，不落临时文件）。

    HTML 在这里重写站址：源文件里写 Pages，上传的那份写镜像。
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in ("demo", "docs"):
            for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, name)):
                dirnames.sort()
                for fn in sorted(filenames):
                    full = os.path.join(dirpath, fn)
                    arc = os.path.relpath(full, ROOT).replace(os.sep, "/")
                    if not _keep(arc):
                        continue
                    info = tar.gettarinfo(full, arc)
                    if fn.endswith(".html"):
                        with open(full, encoding="utf-8") as fh:
                            data = rewrite_hosts(fh.read()).encode("utf-8")
                        info.size = len(data)
                        tar.addfile(info, io.BytesIO(data))
                    else:
                        with open(full, "rb") as fh:
                            tar.addfile(info, fh)
    return buf.getvalue()


def connect() -> paramiko.SSHClient:
    key = paramiko.Ed25519Key.from_private_key_file(KEY)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, pkey=key, timeout=15, banner_timeout=20, auth_timeout=20)
    return client


def check(client: paramiko.SSHClient) -> bool:
    paths = ["/mcd/demo/", "/mcd/docs/about.html"]
    ok = True
    for p in paths:
        cmd = f"curl -s -o /dev/null -w '%{{http_code}}' -H 'Host: {HOST}' http://127.0.0.1{p}"
        _, out, _ = client.exec_command(cmd, timeout=20)
        code = out.read().decode().strip()
        print(f"  {p:<24} {code}")
        ok = ok and code == "200"
    return ok


def social_check() -> bool:
    """抓取器视角自检：页面取得到 → og 说自己是镜像 → 缩略图同源且取得到。

    这一步放在同步末尾，是因为"上传成功"和"转发出去有图"是两件事：
    上一轮的 og-card.jpg 就是文件传上去了、页面却指着另一台主机。
    """
    script = os.path.join(ROOT, "scripts", "check_social.py")
    if not os.path.isfile(script):
        print("跳过抓取自检（找不到 scripts/check_social.py）")
        return True
    # 父进程的输出被管道缓冲时，子进程的日志会抢在前面 —— 先 flush，日志顺序才读得懂。
    sys.stdout.flush()
    return subprocess.run([sys.executable, script, "--base", MIRROR_BASE], check=False).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只做 HTTP 自检")
    ap.add_argument("--no-social", action="store_true", help="跳过抓取器视角自检")
    args = ap.parse_args()

    client = connect()
    try:
        if not args.check:
            data = build_tar()
            print(f"打包 {len(data) / 1e6:.1f}MB → 上传")
            sftp = client.open_sftp()
            with sftp.file("/tmp/mcd-site.tar.gz", "wb") as f:
                f.write(data)
            sftp.close()

            # 保留上一版便于回滚，再解压覆盖
            cmd = (
                f"set -e; rm -rf {REMOTE_DIR}.prev; "
                f"[ -d {REMOTE_DIR} ] && cp -a {REMOTE_DIR} {REMOTE_DIR}.prev || true; "
                f"mkdir -p {REMOTE_DIR}; "
                f"rm -rf {REMOTE_DIR}/demo {REMOTE_DIR}/docs; "
                f"tar -xzf /tmp/mcd-site.tar.gz -C {REMOTE_DIR}; "
                f"du -sh {REMOTE_DIR} | cut -f1"
            )
            _, out, err = client.exec_command(cmd, timeout=120)
            size = out.read().decode().strip()
            msg = err.read().decode().strip()
            if msg:
                print("stderr:", msg[:300])
            print(f"远端站点体积: {size}")

        print("HTTP 自检：")
        ok = check(client)
        print(f"镜像地址: http://{HOST}/mcd/demo/")
        if ok and not args.no_social:
            social_check()
        return 0 if ok else 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
