# WorkBuddy 开发记录（workbuddy.md）

本文件记录「麦门宇宙 McUniverse」在腾讯 WorkBuddy 智能体中的完整开发过程，参与 WorkBuddy 专项奖励。

## 会话一 · 2026-10-22 深夜（作战规划 + 核心引擎）

**用户指令**：深度分析所有项目选出最有潜力的参加 1024 麦当劳程序员创意开发大赛，目标夺得第一；提供麦当劳 MCP Token 联调。

**军师决策过程**：
1. 赛事体检：排名按 GitHub 公开 Star（10-26 00:00 锁榜）；必需 5 件套（README/CONTEST_DECLARATION/MCP_INTEGRATION/mcp-config.example/workbuddy.md）；WorkBuddy 专项奖需提交 workbuddy.md。
2. 榜单情报：104+ 项目；第 1 名 851★；省钱方向 25+ 项目红海；社交货币方向（派对 724/麦门认证 723/年度报告 489）涨星更快。
3. 选题：旧项目无一基于麦当劳 MCP，不可直接参赛；选定「麦门宇宙」= 订单星图 + 麦门人格 + 分享卡，迁移用户既有 Skill（中北大学猫咪档案）的视觉与传播能力。
4. 用户提供 MCP Token，军师当即联调。

**实测发现（2026-10-22 02:30）**：
- MCP 线上工具 35 个（官方文档 33 + 未公开的 query-promotions、query-survey-coupon）；
- 用户账号订单 0 单、积分全 0（新账号）→ 星图引擎设计 0 单降级「星云」状态；
- MCP 返回有三种形态：干净 JSON / text 包装内嵌 JSON / text 表格；营养数据是「JSON 里再套文本表格」的双层包装（已修复并补测试）。

**产出**：
- 参赛申请 Issue #998 已提交；
- `src/mcp_client.py`：MCP 客户端 + 三形态解析器（含二层表格修复）；
- `src/star_model.py`：订单→星图数据模型 + 麦门人格鉴定（7 种人格全正面向）；
- `tests/test_star_model.py`：8 条测试全绿（含零单降伪、双层包装解析）；
- `scripts/fetch_data.py`：真实数据固化（160 餐品营养数据 → samples/）；
- `.gitignore`：Token 与个人订单数据防泄漏。

## 会话二 · 2026-10-23（计划）
Canvas 星图渲染 + 分享卡导出 + SKILL 完善 + 演示页。
