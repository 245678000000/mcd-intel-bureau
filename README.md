# 🕵️ 麦麦情报局 · McIntel Bureau

> **每天一句话，麦麦世界的情报全知道。**
> 基于**麦当劳 MCP** 打造的 WorkBuddy 情报 Skill：活动日历、券情速递、积分体检、抽奖期望值、主题活动雷达——五局合一，只报你该知道的。

**🍔 2026 麦当劳程序员节创意开发大赛参赛作品**

---

## 为什么需要情报局？

麦门信徒的日常痛点：

- 😮‍💨 积分悄悄过期，想起来时已经清零
- 😮‍💨 券包里躺着 8 张券，永远记不住哪张快到期
- 😮‍💨 抽奖活动眼花缭乱，不知道概率值不值
- 😮‍💨 限定活动总在结束后才刷到

**交易工具帮你省钱，情报工具帮你「不漏」。** 麦麦情报局不替你下单，它每天把麦麦世界扫一遍，告诉你：*什么在发生、什么快过期、什么值得动*。

## 五大情报板块

| 板块 | 干什么 | 底层 MCP Tool |
|---|---|---|
| 📅 **活动日历** | 当月活动解读，只挑「进行中 + 7 天内开演」 | `campaign-calendar` |
| 🎫 **券情速递** | 我的券 × 可领券差集，新券播报 + 到期预警 | `available-coupons` `query-my-coupons` `auto-bind-coupons` |
| 🏆 **积分体检** | **即将过期预警** + 最优兑换路线 + 每积分价值锚点 | `query-my-account` `mall-points-products` `mall-create-order` |
| 🎰 **抽奖实验室** | 概率 × 奖池 → 期望值 EV，抽不抽你自己定 | `query-lottery-info` `query-my-prizes` |
| 🎉 **主题雷达** | 城市活动 × 门店 × 场次三级下钻 | `query-party-city/store/date/session` `party-order-create` |

情报分级：🔴 紧急（快过期/快结束）· 🟡 关注 · 🟢 日常。先结论，后细节，数字说话。

## 60 秒上手

**前置**：一个麦当劳 MCP Token（[open.mcd.cn/mcp](https://open.mcd.cn/mcp) 手机号登录 → 控制台 → 激活，免费）+ [WorkBuddy](https://www.workbuddy.cn/)。

```text
① WorkBuddy → 专家·技能·连接器 → 连接器 → 自定义连接器 → 配置 MCP
   粘贴 mcp-config.example.json 内容，把 ${MCD_MCP_TOKEN} 换成你的 Token → 保存并启用

② 把本仓库 skills/mcd-intel-bureau/ 目录导入 WorkBuddy 技能
   （SKILL.md 为技能定义，intel_math.py 为本地精算模块）

③ 对它说：
```

> **「报一下今天的情况」**

局长立刻出勤：时间校准 → 拉日历 → 盘券 → 体检积分 → 算抽奖 EV → 按模板播报简报。

更多问法见 [docs/usage-examples.md](docs/usage-examples.md)。

## 情报样张（示意）

````text
麦麦情报局 · 2026-10-09 简报

一句话局势：你有 1200 积分 14 天后过期，现在动手兑换最划算。

📅 活动日历
  🟡 巨无霸买一送一：10.12–10.14 · 周末限定
  🟢 早餐月卡加赠：进行中 · 至 10.31
🎫 券情速递
  库存 6 张，本周新增 2 张：满 39 减 8（10.20 到期）
  🔴 早餐半价券 3 天后到期
🏆 积分体检
  可用 3850 分｜🔴 1200 分将于 10.23 前过期
  最优兑换路线：大杯拿铁（1500 分）→ 早餐券（1200 分），合计约值 ¥39
  价值锚点：当前商城最高性价比 ≈ 每 1000 积分 13.0 元
🎰 抽奖实验室
  消耗 500 分/次，期望回报 ¥3.2/次 → 🧊 建议积分留着换商品
🎉 主题雷达
  上海档期：麦麦主题派对 × 静安寺店 × 周六 14:00 场 · 手速建议：今晚报点

局长贴士：先把过期的 1200 分换成早餐券，周末买一送一再掏大券。
````

> 样张为演示数据。实际情报以你账户的 MCP 实时返回为准。

## 架构

```mermaid
graph LR
    U[局员] <-->|自然语言| WB[WorkBuddy 局长 SKILL.md]
    WB -->|查询| M[mcd-mcp 麦当劳 MCP Server]
    WB -->|JSON 精算| P[intel_math.py 本地模块]
    P -->|兑换路线 / EV / 券增量| WB
    WB -->|确认门控: 复述动作| U
    M -->|campaign / coupons / points / lottery / party| WB
```

**三段式设计**：读情报（只读工具）→ `intel_math.py` 确定性精算（贪心兑换路线、概率期望值、券差集）→ 确认门控后兑现（领券/兑换/预约均需局员二次确认）。

精算模块零依赖（Python 3 标准库），独立可用：

```bash
python3 skills/mcd-intel-bureau/intel_math.py redeem \
  --points 3850 --expiring 1200 --deadline-days 14 --products products.json

python3 skills/mcd-intel-bureau/intel_math.py lottery --info lottery.json
```

## 目录结构

```text
mcd-intel-bureau/
├── README.md                        # 你正在看
├── CONTEST_DECLARATION.md           # 参赛声明（官方模板）
├── MCP_INTEGRATION.md               # MCP 集成：Tool 清单 / 调用流程 / 数据流
├── mcp-config.example.json          # MCP 配置示例（仅环境变量占位符）
├── workbuddy.md                     # WorkBuddy 开发对话上下文
├── skills/mcd-intel-bureau/
│   ├── SKILL.md                     # 技能定义：人设 / 工作流 / 硬规则
│   ├── briefing.md                  # 简报输出模板
│   └── intel_math.py                # 情报精算核心（零依赖）
└── docs/
    └── usage-examples.md            # 对话示例集
```

## 目标用户

- 🍟 **麦门信徒**：每周至少一顿麦麦，想知道「这周有什么活动」
- 💰 **羊毛学家**：券与积分是资产，资产需要管家
- 🧑‍💻 **AI Agent 玩家**：想看 MCP 落地「每日情报官」这一形态的参考实现

## 声明

- 本项目为 **麦当劳程序员节创意开发大赛** 参赛作品，由参赛者独立开发，**非麦当劳官方产品**。
- 餐品信息、价格、活动以麦当劳官方渠道实时信息为准；项目输出仅供参考，不构成任何专业建议。
- 配置文件仅使用环境变量占位符，不包含任何真实凭证（`CONTEST_DECLARATION.md`）。

## License

[MIT](LICENSE) © 2026 麦麦情报局开发者
