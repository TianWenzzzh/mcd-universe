# MCP 集成说明（MCP Integration）

## 使用的 MCP Server

麦当劳中国官方 MCP Server：`https://mcp.mcd.cn`（Streamable HTTP 协议，Authorization: Bearer Token 鉴权，限流 600 次/分钟）。

## 使用的 Tool 及用途

| Tool | 用途 | 阶段 |
|---|---|---|
| `order-list` | 拉取用户历史订单，作为「麦门星图」的数据源 | P0 核心 |
| `query-order` | 查询订单详情（餐品构成、金额、就餐方式），补全星点属性 | P0 核心 |
| `query-my-account` | 查询积分账户（可用/即将过期），提供「积分哨兵」 | P0 核心 |
| `list-nutrition-foods` | 160 个餐品官方营养数据，构建品类词典与热量着色 | P0 已接入 |
| `campaign-calendar` | 查询当月营销活动日历，驱动「今日麦签」 | P1 |

实测线上共 35 个 Tool（官方文档 33 个，另有未公开的 query-promotions、query-survey-coupon）。

## 调用流程

```
用户本地配置 mcd-mcp（Token 仅存环境变量）
  → order-list 拉取历史订单列表（无参数）
  → query-order 逐单补详情（品类、金额、时段、就餐方式）
  → query-my-account 读取积分状态
  → list-nutrition-foods 构建品类词典
  → 本地引擎：订单解析 → 星图数据模型 → 麦门人格鉴定
  → 渲染「麦门星图」HTML 报告页（纯本地，无外部请求）
  → 一键导出分享卡
```

## 返回格式实测（解析层设计依据）

MCP 实际返回有三种形态，`src/mcp_client.py` 的 `extract_payload()` 统一归一：

1. **干净 JSON**：`structuredContent.data` 为 dict（query-my-account）；
2. **文本包装 JSON**：`content[].text` 内含 "## Original Response" + 内嵌 JSON（order-list / query-order）；
3. **文本表格**：`"[N]{col,col}:"` + CSV 行（list-nutrition-foods）；
4. **二层包装（实测坑）**：形态 2 的 JSON 中 `data` 字段又是形态 3 的文本表格——需二次解析，已修复并有测试覆盖。

## 业务价值

麦当劳 MCP 开放了点餐、订单、积分等原子能力，但单个接口只是数据管道。麦门宇宙把这些原子能力编排成一条「回顾 → 鉴定 → 分享」的情感闭环：让用户看见自己这一年与麦当劳的真实交集，生成可分享的个人星图与人格卡片，同时用积分提醒守住实用价值。数据全程本地处理，Token 不出本机。
