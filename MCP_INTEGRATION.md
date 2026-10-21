# MCP 集成说明（MCP Integration）

## 使用的 MCP Server

麦当劳中国官方 MCP Server：`https://mcp.mcd.cn`（Streamable HTTP 协议，Authorization: Bearer Token 鉴权）。

## 使用的 Tool 及用途

| Tool | 用途 | 阶段 |
|---|---|---|
| `order-list` | 拉取用户历史订单（近一年），作为「麦门星图」的数据源 | P0 核心 |
| `query-order` | 查询订单详情（餐品构成、金额、就餐方式），补全星点属性 | P0 核心 |
| `query-my-account` | 查询积分账户（可用/即将过期），提供「积分到期提醒」实用功能 | P0 核心 |
| `campaign-calendar` | 查询当月营销活动日历，驱动「今日麦签」 | P1 |
| `list-nutrition-foods` | 获取餐品营养数据，为星图上色（品类/热量维度） | P1 |

## 调用流程

```
用户授权配置 mcd-mcp（本地 MCP Client）
  → order-list 拉取历史订单列表
  → query-order 逐单补详情（品类、金额、时段、就餐方式）
  → query-my-account 读取积分状态
  → 本地引擎：订单解析 → 星图数据模型 → 麦门人格鉴定
  → 渲染「麦门星图」HTML 报告页（纯本地，无外部请求）
  → 一键导出分享卡
```

## 业务价值

麦当劳 MCP 开放了点餐、订单、积分等原子能力，但单个接口只是数据管道。麦门宇宙把这些原子能力编排成一条「回顾 → 鉴定 → 分享」的情感闭环：让用户看见自己这一年与麦当劳的真实交集，生成可分享的个人星图与人格卡片，同时用积分提醒守住实用价值。数据全程本地处理，Token 不出本机。
