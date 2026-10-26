#!/usr/bin/env bash
# 麦门宇宙 · 国内镜像一键部署（Ubuntu/Debian，幂等可重复执行）
#
# 用法（在服务器上）：
#   curl -fsSL https://raw.githubusercontent.com/TianWenzzzh/mcd-universe/main/deploy/setup.sh | sudo bash
#   或已克隆仓库时：sudo bash deploy/setup.sh
#
# 产物：
#   http://<公网IP>:8080/            → 演示页（demo/index.html）
#   http://<公网IP>:8080/docs/about.html → 作品说明页
#
# 说明：监听 8080 而非 80，避免域名备案问题；需在阿里云安全组放行 8080/tcp。

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/TianWenzzzh/mcd-universe.git}"
SRC_DIR="${SRC_DIR:-/opt/mcuniverse-src}"
WEB_DIR="${WEB_DIR:-/var/www/mcuniverse}"
PORT="${PORT:-8080}"

echo "==> 1/5 安装依赖（nginx / git / curl）"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx git curl ca-certificates >/dev/null

echo "==> 2/5 拉取代码到 ${SRC_DIR}"
if [ -d "${SRC_DIR}/.git" ]; then
  git -C "${SRC_DIR}" fetch --depth=1 origin main
  git -C "${SRC_DIR}" reset --hard origin/main
else
  rm -rf "${SRC_DIR}"
  git clone --depth=1 "${REPO_URL}" "${SRC_DIR}"
fi

echo "==> 3/5 发布静态文件到 ${WEB_DIR}"
mkdir -p "${WEB_DIR}"
rm -rf "${WEB_DIR:?}/demo" "${WEB_DIR:?}/docs"
cp -r "${SRC_DIR}/demo" "${WEB_DIR}/demo"
cp -r "${SRC_DIR}/docs" "${WEB_DIR}/docs"
# 站点根路径直接进演示页
cat > "${WEB_DIR}/index.html" <<'HTML'
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=./demo/"><title>麦门宇宙 McUniverse</title></head>
<body style="background:#05040e;color:#ffe9a8;font-family:sans-serif;text-align:center;padding:80px">
正在进入麦门宇宙… <a href="./demo/" style="color:#ffd97a">点此进入</a></body></html>
HTML

echo "==> 4/5 写 nginx 配置（监听 ${PORT}）"
cat > /etc/nginx/sites-available/mcuniverse <<NGINX
server {
    listen ${PORT} default_server;
    listen [::]:${PORT} default_server;
    server_name _;
    root ${WEB_DIR};
    index index.html;

    gzip on;
    gzip_types text/html text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    # HTML 不缓存，静态资源长缓存
    location ~* \.html$ { add_header Cache-Control "no-cache"; }
    location ~* \.(png|gif|jpg|jpeg|webp|svg|woff2?)$ {
        add_header Cache-Control "public, max-age=604800";
    }

    location / { try_files \$uri \$uri/ =404; }
    add_header X-Content-Type-Options "nosniff";
}
NGINX
ln -sf /etc/nginx/sites-available/mcuniverse /etc/nginx/sites-enabled/mcuniverse
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> 5/5 自检"
IP="$(curl -fsS --max-time 5 https://api.ipify.org || echo 127.0.0.1)"
for path in "/" "/demo/" "/docs/about.html"; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}${path}" || true)"
  printf '  %-22s %s\n' "${path}" "${code}"
done

echo
echo "完成。站点地址： http://${IP}:${PORT}/"
echo "提醒：需在云厂商安全组放行 ${PORT}/tcp，否则公网访问不到。"
