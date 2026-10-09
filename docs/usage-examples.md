# 对话示例 · usage-examples

以下为「麦麦情报局」的典型问法与局长行为（数据为示意，以账户实际返回为准）。

## 1. 今日简报

> 局员：报一下今天的情况

局长依次调用 `now-time-info → campaign-calendar → available-coupons → query-my-coupons → query-my-account → query-lottery-info`，
存在过期积分时追加 `mall-points-products` 并调用 `intel_math.py redeem`，
最后按 [briefing.md](../skills/mcd-intel-bureau/briefing.md) 模板输出简报。

## 2. 积分专项体检

> 局员：帮我盘一下积分

局长：
1. `query-my-account` + `mall-points-products`（必要时 `mall-product-detail`）
2. `intel_math.py redeem --points 3850 --expiring 1200 ...`
3. 播报：**最优兑换路线 + 每积分价值锚点 + 浪费预警**
4. 局员选定商品 → 局长复述「将消耗 1500 积分兑换大杯拿铁，确认？」→ 确认后 `mall-create-order`

## 3. 抽奖值不值

> 局员：这期抽奖值得抽吗？

局长：`query-lottery-info` → `intel_math.py lottery` → 播报 EV 与结论（🎯/🧊）。
若局员说「帮我抽一次」→ 复述消耗 → 确认后 `draw-lottery`。

## 4. 主题活动雷达

> 局员：上海最近有什么主题活动？

局长：`query-party-city` 确认上海有档期 → `query-party-store(上海)` → `query-partystore-date(门店)` → `query-partystore-session(日期)`，
输出「活动 × 门店 × 场次」表。局员选定 → 复述 → `party-order-create`。

## 5. 一键领券

> 局员：一键领券

局长：先 `available-coupons` 展示将领取的券清单 → 复述「将自动领取全部 4 张可领券」→ 确认后 `auto-bind-coupons`。

## 6. 追问单条情报

> 局员：只看券

局长：只走券情板块（`available-coupons` + `query-my-coupons` → `intel_math.py coupon`），不拉其他情报。
