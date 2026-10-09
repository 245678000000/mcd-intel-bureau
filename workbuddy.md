# workbuddy.md · WorkBuddy 开发对话上下文

> ⚠️ **待办**：本文件需替换为 WorkBuddy 中的**真实开发/使用对话导出**（用于核验联动奖励条件）。
> 在 WorkBuddy 中完成下方「导出流程」后，把导出的对话内容粘贴替换本说明，再提交/更新仓库。

## 导出流程（5 分钟）

1. WorkBuddy → 专家·技能·连接器 → 连接器 → 自定义连接器 → 配置 MCP，粘贴 `mcp-config.example.json` 内容（把 `${MCD_MCP_TOKEN}` 替换为你的真实 Token）→ 保存 → 启用 `mcd-mcp`。
2. 新开对话，依次发送下面三段提示词（真实跑通会触发 MCP 工具调用）：

**第 1 段（功能验证）**

```text
你是「麦麦情报局」局长，请严格按 skills/mcd-intel-bureau/SKILL.md 的人设和流程工作。
现在执行流程 A「今日简报」：依次调用 now-time-info、campaign-calendar、
available-coupons、query-my-coupons、query-my-account、query-lottery-info，
有过期积分就拉 mall-points-products 并用 intel_math.py 算兑换路线，
最后按 briefing.md 模板播报。
```

**第 2 段（积分专项 + 精算模块）**

```text
帮我盘一下积分：用 query-my-account 和 mall-points-products 取数，
调用 intel_math.py redeem（stdin 模式）算最优兑换路线，
播报路线和每积分价值锚点。先不要兑换任何东西。
```

**第 3 段（确认门控验证）**

```text
抽奖实验室：用 query-lottery-info 取本期奖池，调 intel_math.py lottery 算期望值，
告诉我抽不抽。我如果说抽，你必须先复述消耗再问我确认。
```

3. 对话完成后，导出该对话（WorkBuddy 会话导出/复制全文），替换本文件内容并保留本行以上标题。

---
（以下由真实导出内容替换）
