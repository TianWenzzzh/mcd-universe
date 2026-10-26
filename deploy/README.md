# 国内镜像部署（可选）

GitHub Pages 在国内网络下实测首屏 2–18s，评委体验打折。这里提供一份可选的国内镜像方案：把同一份静态站点部署到自己的 Ubuntu 云服务器，走 8080 端口（避免域名备案）。

## 一条命令

在服务器上执行：

```bash
curl -fsSL https://raw.githubusercontent.com/TianWenzzzh/mcd-universe/main/deploy/setup.sh | sudo bash
```

脚本做的事（幂等，可重复执行）：

1. 安装 nginx / git
2. 浅克隆仓库到 `/opt/mcuniverse-src` 并更新到最新 main
3. 发布 `demo/` 与 `docs/` 到 `/var/www/mcuniverse`（根路径重定向到演示页）
4. 写 nginx 站点配置（8080、gzip、HTML 不缓存 / 静态资源长缓存）
5. 自检三个路径并打印访问地址

## 必须做的一步

在云厂商控制台的**安全组**放行 `8080/tcp`，否则公网访问不通：

- 阿里云：ECS → 安全组 → 配置规则 → 入方向 → 添加 8080/8080，授权对象 0.0.0.0/0

## 验证

```bash
curl -sI http://127.0.0.1:8080/demo/ | head -5
```

## 更新

仓库有新提交后，再执行一次同一条命令即可（脚本会 `reset --hard origin/main`）。

## 与 GitHub Pages 的关系

GitHub Pages 仍是主站与评审默认入口；国内镜像只是**加速副本**，两者内容逐字节一致（同一份 `demo/`、`docs/`）。因此镜像挂掉不影响评审，反之亦然。
