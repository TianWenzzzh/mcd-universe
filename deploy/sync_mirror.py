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
import sys
import tarfile

import paramiko

HOST = os.environ.get("MCD_MIRROR_HOST", "47.114.38.125")
USER = os.environ.get("MCD_MIRROR_USER", "root")
KEY = os.path.expanduser(os.environ.get("MCD_MIRROR_KEY", "~/.ssh/mcuniverse_deploy"))
REMOTE_DIR = os.environ.get("MCD_MIRROR_PATH", "/opt/caddy/config/mcd-site")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# docs/assets 里"页面真的会去取"的单列文件：体积小、少一张就少一块功能。
# og-card.jpg 是说明页与演示页的 og:image —— 漏了它，镜像链接转进微信就是一张灰卡
# （线上实测 404，白名单只认 *-web.jpg 的那一版一直在悄悄漏传）。
REFERENCED_ASSETS = ("demo-poster.jpg", "og-card.jpg")


def _filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """docs/assets 只上传 Web 优化版（*-web.jpg / *-web.gif）与页面引用的小图。

    原图（2 倍 PNG、未压缩 GIF）只用于投稿材料上传，不必占用镜像带宽。
    """
    path = tarinfo.name.replace("\\", "/")
    if "/assets/" in path and not path.endswith(("/",)):
        allowed = path.endswith(("-web.jpg", "-web.gif", ".mp4", *REFERENCED_ASSETS))
        if not allowed:
            return None
    return tarinfo


def build_tar() -> bytes:
    """把 demo/ 与 docs/ 打成 tar.gz（内存中完成，不落临时文件）。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in ("demo", "docs"):
            tar.add(os.path.join(ROOT, name), arcname=name, filter=_filter)
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只做 HTTP 自检")
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
        return 0 if ok else 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
