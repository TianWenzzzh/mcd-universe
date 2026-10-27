# 国内镜像部署（当前线上形态）

> 主站：GitHub Pages `https://tianwenzzzh.github.io/mcd-universe/`
> 镜像：阿里云杭州 ECS `http://47.114.38.125/mcd/demo/`（裸 IP，免备案）

## 为什么需要镜像

国内网络实测（2026-10-27，8 次取中位）：

| 页面 | GitHub Pages | 国内镜像 |
|---|---|---|
| 演示页首屏 | 1.4–3.6 s | 0.21–0.27 s |
| 作品说明页 | 1.07 s | 0.12 s |

镜像快 5–13 倍。GitHub Pages 仍是主入口（评审默认点这个），镜像是加速副本，两者内容一致。

## 这台服务器上实际长什么样

服务器不是空的：同时跑着「研伴」的 7 个 Docker 容器、MySQL、Redis，以及**中北喵星图**（`/cat/`）。本项目**纯增量**挂载，不碰任何现有服务。

- 反代：Caddy（容器 `caddy-https`），配置 `/opt/caddy/Caddyfile`
- 挂载：`/opt/caddy/config/mcd-site`（容器内 `/config/mcd-site`）
- 路由：HTTP 裸 IP 的 `/mcd/*`（沿用 `/cat/*` 的既有模式）
- 说明：`docs/` 与 `demo/` 原样发布，`/mcd/` 与 `/mcd/demo/` 均 302 到演示页

Caddyfile 增量片段（已上线，勿重复添加）：

```caddyfile
	# [ADD-mcuniverse 2026-10-27] 麦门宇宙：http://47.114.38.125/mcd/
	@mcdbare path /mcd
	redir @mcdbare /mcd/ 302
	@mcdroot path /mcd/
	redir @mcdroot /mcd/demo/ 302
	handle_path /mcd/* {
		root * /config/mcd-site
		file_server
		encode gzip
	}
```

## 同步方式（免密）

一次性配置：本机 `~/.ssh/mcuniverse_deploy` 私钥，公钥已加入服务器 `root/.ssh/authorized_keys`（注释 `mcuniverse-deploy`）。撤销：删除该行即可。

```bash
python deploy/sync_mirror.py           # 打包上传 + HTTP 自检
python deploy/sync_mirror.py --check   # 只自检
```

- 只上传 `demo/` 与 `docs/`；`docs/assets` 走白名单（`*-web.jpg`、`*-web.gif`、`.mp4`、`demo-poster.jpg`、`og-card.jpg`），原图不进镜像
- 上传前保留上一版到 `mcd-site.prev` 便于回滚
- 结束会自检 `/mcd/demo/` 与 `/mcd/docs/about.html`，非 200 即失败退出

## 回滚

```bash
# 站点文件回滚
ssh -i ~/.ssh/mcuniverse_deploy root@47.114.38.125 \
  'rm -rf /opt/caddy/config/mcd-site && cp -a /opt/caddy/config/mcd-site.prev /opt/caddy/config/mcd-site'

# Caddyfile 回滚（自动备份在 /opt/caddy/Caddyfile.bak-*）
ssh -i ~/.ssh/mcuniverse_deploy root@47.114.38.125 \
  'ls -t /opt/caddy/Caddyfile.bak-* | head -1 | xargs -I{} cp {} /opt/caddy/Caddyfile && docker exec caddy-https caddy reload --config /etc/caddy/Caddyfile'
```

## 带宽约束（重要）

ECS 出口实测约 **1.3 Mbps**。因此：

- 页面资源全部转 Web 优化版（2 倍 PNG → 渐进式 JPEG，1.45MB → 80KB；GIF → H.264 MP4，1.1MB → 104KB）
- 镜像全站约 **2.1 MB**，说明页首屏约 500KB（≈3s）
- 大图/视频不要回退成原始 PNG/GIF，否则单文件就要 5–7 秒

## 另：空服务器的 nginx 方案

`deploy/setup.sh` 是给**干净 Ubuntu** 用的一键脚本（nginx :8080），当前这台机器**未使用**（已有 Caddy，且 8080 被研伴占用），仅作备用。
