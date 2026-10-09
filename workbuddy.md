# workbuddy.md · WorkBuddy 开发对话上下文

> 导出自 WorkBuddy 会话工作区（2026-10-09 17:34:40 导出），含当日工作日志与真机 MCP 数据文件。
> 会话内容：配置 mcd-mcp 连接器 → 执行「今日简报」数据采集 → 流程 B 积分专项体检 → 抽奖实验室。
> 敏感信息（账户号）已脱敏；MCP Token 仅存于本机 ~/.workbuddy/mcp.json（权限 600），不出现在任何导出中。

---

# 2026-10-09工作日志

## 配置麦当劳官方 MCP（mcd-mcp）

- 在 `~/.workbuddy/mcp.json` 新建配置（此前文件不存在），写入 streamablehttp 类型的 `mcd-mcp` 服务器
- URL: `https://mcp.mcd.cn`，使用 Bearer Token 认证
- 端点实测通过：HTTP 200，`serverInfo` = `mcd-mcp v1.0.0`，协议版本 2025-06-18
- 文件权限收紧为 `600`（内含明文 token）
- 注意：写入后需在连接器管理页手动点「信任」才会激活

## 执行「今日简报」数据采集

调用 mcd-mcp 工具链完成只读采集：now-time-info、query-my-account、campaign-calendar、query-lottery-info、available-coupons、query-my-coupons、mall-points-products。

关键数据：
- 账户 02006722******5935（已脱敏）：可用积分 102.6，累计 411.7，已过期 309.1，本月/下月将过期均为 0
- 卡包 14 张券，其中「麦旋风任选」¥9.9与「薯薯任选」¥9.9 今日 23:59 到期
- 抽奖活动 dtx2进行中，单次 24 积分，最多可抽 4 次

积分兑换结论（102.6 积分，在架商品）：
- 推荐路线 B：17073(6.9元可乐麦炫酷) + 17074(6.9元香芋派/菠萝派任选) = 100 积分换 13.8 元价值，性价比 0.138 元/分
- 备选路线 A：17076(10.9元指定小食任选) = 100 积分换 10.9 元，差 2.9 元
- 多个低价商品（15866/6110/6111）已于 2026-03~06 下架，不可兑换

## 待办

- ~~`skills/mcd-intel-bureau/` 目录不存在~~ → **已解决**：实际路径是 `/Users/tiantian/ZCodeProject/mcd-intel-bureau/skills/mcd-intel-bureau/`，SKILL.md / briefing.md / intel_math.py 三件套齐全。第一轮搜索时 `find` 被沙箱 SIGTERM 打断，漏掉了 ZCodeProject。教训：搜索要用限定深度 + 分路径的方式，别一次扫全盘。

## 流程 B「积分专项体检」执行记录

-取数：query-my-account（可用 102.6/ 累计 411.7 / 已过期 309.1 / 本月下月过期均为 0）、mall-points-products（在架商品 7 个）
- 调用：`intel_math.py redeem` stdin 模式，JSON 协议 `{"task":"redeem","points","expiring","deadline_days","products"}`
- 最优路线：17073(6.9元可乐麦炫酷) + 17074(6.9元香芋派/菠萝派任选) = 100 积分 → 13.8 元，剩 2.6 分
- 每积分价值锚点：0.1380 元/积分（每千积分 138 元），这是全商城最高档；其余档位 17076=0.109、17077=0.0545、17080=0.0358、17079=0.0338、17081=0.0274
- 未执行任何写操作（无mall-create-order）

### intel_math.py 归一化坑（重要）

SKILL.md 第 72 行称「MCP 字段与模块字段的归一化由模块内部兼容，Agent 只需原样传递业务数组」——**这是错的**。

实测：直接传 MCP 原始字段（`spuName` / `point` / `price`）跑 redeem，结果为
- 名称全部落到「未命名商品」（模块只认 `name`/`title`/`productName`，不认 `spuName`）
- `cash_value` 全为 0（模块取 `price`/`cash_value`，而 MCP 的 `price` 对积分商品恒为 "0"）
- 结果 value_per_point 全 0，路线完全错误但**不报错**——静默失败，最危险

正确做法：Agent 侧归一化后再喂。字段映射：
- `spuName` → `name`
- `point` → `points`
- 现金价值需从商品名称解析（如「6.9元可乐麦炫酷」→ `cash_value: 6.9`），不能直接用 MCP 的 `price`
- `id` ← `spuId`
- 需额外剔除 `downTime` 已过期的商品：MCP 的 `status` 字段对已下架商品仍返回 2，不可信

## 抽奖实验室（流程 A 第5 步 / 独立查询）

活动 dtx2「麦麦积分抽奖」：进行中（2025-01-26 ~ 2030-12-31），单次 24 积分纯积分消耗，
`drawDecision.resourceEligible=true`，`nextConsumption` = POINTS 24。奖池 10 档全是券+积分，无实物大奖。

**intel_math.py lottery 同样有归一化坑**：
- 模块要 `cost_points`，MCP 给的是 `drawPoint` → 第一次跑直接报「缺奖品列表或消耗规则」
- 模块要 `probability`/`rate`/`winRate`，**MCP 的 query-lottery-info 根本不返回概率字段**
- 补上 cost_points 后能跑出结构，但 10 个奖品 probability/cash_value 全为 0，
  `ev_net_cny` 算出 -0.24 → advice「把积分留着换商城更划算」
- **这个 -0.24 是伪结论**，不能采信。真实 EV 无法从现有 MCP 接口算出

替代方案：改用敏感性分析（假设中奖率档位 × 券面值推演），结论是只要中奖率 ≥20% 且券均面值 ≥1.2 元，抽奖就优于兑换。但中奖率属于官方未公开信息。

结论倾向：不建议为抽奖专门消耗积分；若要玩，按你确认后一次抽 1 次试水，不要连抽（有频次限制）。

---

## 附：真机 MCP 数据文件（导出自会话工作区 tmp/）

### tmp/products_raw.json（mall-points-products 原始返回）

```json
[
{"spuId":17073,"spuName":"6.9元可乐麦炫酷","point":"50","price":"0","status":2,"downTime":"2026-12-30 23:59:59","shopId":2},
{"spuId":17074,"spuName":"6.9元香芋派/菠萝派任选","point":"50","price":"0","status":2,"downTime":"2026-12-30 23:59:59","shopId":2},
{"spuId":17076,"spuName":"10.9元指定小食任选","point":"100","price":"0","status":2,"downTime":"2026-12-30 23:59:59","shopId":2},
{"spuId":17077,"spuName":"10.9元指定小食任选","point":"200","price":"0","status":2,"downTime":"2026-12-30 23:59:59","shopId":2},
{"spuId":17079,"spuName":"16.9元麦辣可乐组合","point":"500","price":"0","status":2,"downTime":"2026-12-30 23:59:59","shopId":2},
{"spuId":17080,"spuName":"17.9元板烧可乐组合","point":"500","price":"0","status":2,"downTime":"2026-12-30 23:59:59","shopId":2},
{"spuId":17081,"spuName":"21.9元巨无霸可乐组合","point":"800","price":"0","status":2,"downTime":"2026-12-30 23:59:59","shopId":2}
]
```

### tmp/lottery_raw.json（query-lottery-info 原始返回）

```json
{
  "activityCode": "dtx2",
  "activityName": "麦麦积分抽奖",
  "activityStatusText": "进行中",
  "beginTime": "2025-01-26 00:00:00",
  "endTime": "2030-12-31 23:59:59",
  "drawPoint": "24",
  "drawTypeText": "消耗积分抽奖",
  "availablePoint": "102.6",
  "prizes": [
    {"name": "下单立减3元券", "typeText": "优惠券"},
    {"name": "下单立减2元券", "typeText": "优惠券"},
    {"name": "下单立减1元券", "typeText": "优惠券"},
    {"name": "麦辣三件套5折券", "typeText": "优惠券"},
    {"name": "板烧三件套5折券", "typeText": "优惠券"},
    {"name": "双层鳕鱼三件套6折券", "typeText": "优惠券"},
    {"name": "甜辣小食组合5折券", "typeText": "优惠券"},
    {"name": "小食四件套5.5折券", "typeText": "优惠券"},
    {"name": "麦旋风5折券", "typeText": "优惠券"},
    {"name": "30积分", "typeText": "积分奖"}
  ]
}
```

---

## 会话后修复记录（2026-10-09，intel_math.py v1.1）

本次真机会话暴露的两个归一化缺口，已在会话后合入 `intel_math.py`：

1. 商品归一化：直接支持 `spuId`/`spuName`/`point`/`downTime`；`price` 恒为 "0" 时忽略，
   现金价值从 `spuName` 前缀解析；下架判定改用 `downTime`（`status` 不可信）。
2. 抽奖模块：消耗积分新增 `drawPoint` 别名；检测到无概率数据时自动切换
   盈亏平衡敏感性模式（需 `point_value` 锚点），拒绝输出伪 EV。

修复后用本会话的原始数据回归验证：redeem 直传 raw 字段输出与 Agent 侧归一化结果一致
（100 积分 → 13.8 元，锚点 0.138 元/分）。
