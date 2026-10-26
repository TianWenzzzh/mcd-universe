# Contributing

感谢关注「麦门宇宙」。本项目是 1024 程序员节参赛作品，同时欢迎任何形式的改进。

## 开发环境

运行时零依赖（仅 Python 3.10+ 标准库）。开发工具：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate  |  macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
```

## 常用命令

```bash
ruff check .          # 静态检查
ruff format .         # 格式化
pytest                # 测试（34 条）
python scripts/lint_template.py   # 渲染模板静态检查（未定义函数 / 缺失 DOM 引用）
python scripts/check_links.py      # 页面间链接完整性（相对路径解析）

# 重建四个演示页（改动 templates/starmap.html 后必须跑，否则线上还是旧页面）
python scripts/build_demo.py
python scripts/build_demo.py --check   # 只校验；CI 会跑这一步，产物与模板不同步即失败

# 单页生成（无需 Token）
python scripts/generate_report.py --demo samples/demo_orders.json -o demo/index.html

# 拉取本人真实订单（需要环境变量 MCD_MCP_TOKEN，Token 永不入库）
export MCD_MCP_TOKEN="your_token_here"
python scripts/generate_report.py --live -o report.html
```

## 浏览器 E2E（可选，需要 Node + playwright-core）

```bash
npm i -D playwright-core   # 或使用已安装 Edge/Chrome 的 channel
node scripts/e2e_check.mjs  # 六类断言：五态冒烟、四风格分享卡导出、导出后屏幕构图复位、
                            # 真实点击/键盘/悬停、导出面板焦点循环、切换器 aria-current、移动端 HUD 重叠
node scripts/card_audit.mjs # 分享卡像素体检：空洞带 / 二维码与文案间距 / 脚注下边距（改版式后跑一遍并肉眼验收产物）

# 投稿截图与 README 动图（可复现重拍；GIF 需要 ffmpeg，可用 pip install imageio-ffmpeg 取二进制）
node scripts/make_shots.mjs [baseUrl] [outDir]
FFMPEG=<ffmpeg 路径> node scripts/make_gif.mjs [baseUrl] [out.gif]
```

## 代码约定

- **零运行时依赖**：`src/` 只用标准库，不引入第三方包；
- **类型标注**：公开函数必须有类型标注；
- **测试先行**：修 bug 先写能复现的测试，再修；
- **Token 红线**：任何情况下不把 `MCD_MCP_TOKEN` 写入文件、日志或提交；
- **数据红线**：真实订单数据只允许本地处理，演示数据必须匿名化；
- **中文注释**：工程注释用中文，与项目语境一致。

## 提交 PR

1. Fork → 分支（`feat/xxx` 或 `fix/xxx`）
2. 保证 `ruff check .`、`pytest`、`python scripts/lint_template.py` 全绿
3. PR 描述里写清动机与验证方式
