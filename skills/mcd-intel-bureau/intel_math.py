#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦情报局 · 情报计算核心 (intel_math.py)

纯本地确定性计算模块，不直接访问网络。
Agent（WorkBuddy）通过麦当劳 MCP 拉取原始数据后，把 JSON 交给本模块做精算，
输出结构化结论供播报使用。

用法一（命令行）:
    python3 intel_math.py redeem  --points 3850 --expiring 1200 --deadline-days 14 --products products.json
    python3 intel_math.py lottery --info lottery.json
    python3 intel_math.py coupon  --mine my_coupons.json --available available.json

用法二（stdin / agent 模式）:
    echo '{"task":"redeem", ...}' | python3 intel_math.py -

所有输入输出均为 JSON（stdout），退出码 0 表示成功。
"""

import argparse
import json
import sys
from datetime import datetime, timedelta

# ── 工具函数 ────────────────────────────────────────────────────────────────


def _load_json(path_or_data):
    """支持文件路径或已解析的对象。"""
    if isinstance(path_or_data, (dict, list)):
        return path_or_data
    with open(path_or_data, "r", encoding="utf-8") as f:
        return json.load(f)


def _clean_number(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _norm_products(raw):
    """归一化 mall-points-products / mall-product-detail 的返回。

    兼容字段别名：point/points/needPoint -> points；
    price/value/cash -> cash_value；title/productName/name -> name。
    """
    items = raw if isinstance(raw, list) else raw.get("items") or raw.get("list") or raw.get("products") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        points = _clean_number(it.get("points", it.get("point", it.get("needPoint"))))
        cash = _clean_number(it.get("cash_value", it.get("price", it.get("cash"))))
        name = it.get("name") or it.get("title") or it.get("productName") or "未命名商品"
        if points <= 0:
            continue  # 无法计算积分性价比的商品跳过
        out.append(
            {
                "id": it.get("id") or it.get("productId") or it.get("code"),
                "name": name,
                "points": points,
                "cash_value": cash,
                "value_per_point": round(cash / points, 4),
                "stock": it.get("stock", it.get("inventory", "")),
            }
        )
    out.sort(key=lambda x: -x["value_per_point"])
    return out


# ── 模块 1：积分最优兑换路线 ────────────────────────────────────────────────


def plan_redemption(total_points, expiring_points, products, deadline_days=14):
    """贪心规划兑换路线：优先消耗「即将过期积分」，其次总积分性价比。

    返回：建议兑换清单、消耗积分、剩余积分、浪费预警。
    """
    total_points = _clean_number(total_points)
    expiring = min(_clean_number(expiring_points), total_points)
    ranked = _norm_products(products)
    if not ranked:
        return {"error": "没有可用积分商品数据"}

    plan, used, used_by_expiry = [], 0, 0
    for p in ranked:
        remain_total = total_points - used
        if remain_total < p["points"]:
            continue
        # 过期积分优先原则：先用快过期的额度兑换高价值商品
        cover = min(p["points"], expiring - used_by_expiry)
        plan.append(
            {
                "name": p["name"],
                "points": p["points"],
                "cash_value": p["cash_value"],
                "value_per_point": p["value_per_point"],
                "covered_by_expiring": cover,
            }
        )
        used += p["points"]
        used_by_expiry += cover
        if used >= total_points * 0.95:
            break

    wasted = max(0, expiring - used)
    plan.sort(key=lambda x: (-x["covered_by_expiring"], -x["value_per_point"]))
    best_vpp = ranked[0]
    return {
        "summary": f"可用积分 {total_points:g}，其中 {expiring:g} 分将在约 {deadline_days} 天内过期",
        "redeem_plan": plan[:5],
        "points_used": used,
        "points_left": round(total_points - used),
        "total_cash_value": round(sum(x["cash_value"] for x in plan), 2),
        "best_value_product": {
            "name": best_vpp["name"],
            "value_per_point": best_vpp["value_per_point"],
            "hint": f"每 1000 积分约值 {best_vpp['value_per_point'] * 1000:.1f} 元",
        },
        "expiry_alert": (
            f"⚠️ 有 {wasted:g} 过期积分当前方案覆盖不到，建议优先兑换小额商品消化"
            if wasted > 0
            else "✅ 过期积分已被兑换路线完整覆盖"
        ),
    }


# ── 模块 2：抽奖期望值实验室 ───────────────────────────────────────────────


def _parse_probability(raw):
    """概率解析：兼容 '0.5%' 字符串、0.005 小数、15（百分比）、5000（万分比）。"""
    if isinstance(raw, str):
        s = raw.strip()
        pct = s.endswith("%")
        v = _clean_number(s.rstrip("%").strip())
        return v / 100.0 if pct else v
    v = _clean_number(raw)
    if v <= 1:
        return v  # 已是小数概率
    if v <= 100:
        return v / 100.0  # 百分比数值
    return v / 10000.0  # 万分比数值


def lottery_ev(info):
    """计算积分抽奖的期望值（EV）与回本概率框架。

    输入：query-lottery-info 的返回（奖品列表/消耗规则）。
    输出：EV（积分计价 + 现金计价）、结论建议。
    """
    prizes = info.get("prizes") or info.get("prizeList") or info.get("activityPrizes") or []
    cost_points = _clean_number(
        info.get("cost_points", info.get("consumePoints", info.get("drawCostPoints"))), default=-1
    )
    if not prizes or cost_points < 0:
        return {"error": "抽奖活动数据不完整（缺奖品列表或消耗规则）"}

    total_prob, ev_cash, table = 0.0, 0.0, []
    for pz in prizes:
        name = pz.get("name") or pz.get("prizeName") or "未知奖品"
        prob = _parse_probability(pz.get("probability", pz.get("rate", pz.get("winRate"))))
        cash = _clean_number(pz.get("cash_value", pz.get("price", pz.get("worth"))))
        total_prob += prob
        ev_cash += prob * cash
        table.append(
            {
                "name": name,
                "probability": round(prob, 6),
                "cash_value": cash,
                "contribution": round(prob * cash, 4),
            }
        )

    # 积分成本折算：默认 1000 积分 ≈ 10 元（可在参数覆盖）
    point_to_cny = _clean_number(info.get("point_to_cny"), default=0.01)
    cost_cash = cost_points * point_to_cny
    ev_net = ev_cash - cost_cash
    advice = (
        "🎯 期望为正，长期看值得一抽（但单次方差极大，理性摸奖）"
        if ev_net > 0
        else "🧊 期望为负，把积分留着换商城商品更划算"
    )
    return {
        "draw_cost_points": cost_points,
        "draw_cost_cny_estimate": round(cost_cash, 2),
        "ev_gross_cny": round(ev_cash, 4),
        "ev_net_cny": round(ev_net, 4),
        "prize_table": sorted(table, key=lambda x: -x["probability"]),
        "probability_sum": round(total_prob, 6),
        "probability_note": (
            "中奖概率之和 < 1，差额为谢谢参与"
            if total_prob < 0.999
            else "概率之和 = 1，人人有奖型抽奖"
        ),
        "advice": advice,
    }


# ── 模块 3：券情雷达 ───────────────────────────────────────────────────────


def coupon_radar(mine, available):
    """我的券 × 可领券 → 库存与增量摘要。"""
    def _list(x):
        if isinstance(x, list):
            return x
        return x.get("coupons") or x.get("list") or x.get("items") or [] if isinstance(x, dict) else []

    mine_l, avail_l = _list(mine), _list(available)
    def _key(c):
        return c.get("title") or c.get("name") or c.get("couponName") or "未命名券"
    mine_names = {_key(c) for c in mine_l}
    new_coupons = [c for c in avail_l if _key(c) not in mine_names]
    return {
        "my_coupon_count": len(mine_l),
        "claimable_count": len(avail_l),
        "new_to_me": [
            {
                "title": _key(c),
                "threshold": c.get("threshold") or c.get("minConsume") or "",
                "discount": c.get("discount") or c.get("amount") or c.get("value") or "",
                "expire": c.get("expireTime") or c.get("validEndDate") or "",
            }
            for c in new_coupons[:8]
        ],
        "hint": "发现新券可直接说「一键领券」触发 auto-bind-coupons" if new_coupons else "券池无增量，坐等下周上新",
    }


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(description="麦麦情报局 · 情报计算核心")
    sub = ap.add_subparsers(dest="task", required=True)

    r = sub.add_parser("redeem", help="积分最优兑换路线")
    r.add_argument("--points", required=True, type=float)
    r.add_argument("--expiring", default=0, type=float)
    r.add_argument("--deadline-days", default=14, type=int)
    r.add_argument("--products", required=True, help="mall-points-products 返回的 JSON 文件")

    l = sub.add_parser("lottery", help="抽奖期望值")
    l.add_argument("--info", required=True, help="query-lottery-info 返回的 JSON 文件")

    c = sub.add_parser("coupon", help="券情雷达")
    c.add_argument("--mine", required=True)
    c.add_argument("--available", required=True)

    sub.add_parser("-", help="stdin JSON 模式")

    args = ap.parse_args()
    try:
        if args.task == "redeem":
            out = plan_redemption(args.points, args.expiring, _load_json(args.products), args.deadline_days)
        elif args.task == "lottery":
            out = lottery_ev(_load_json(args.info))
        elif args.task == "coupon":
            out = coupon_radar(_load_json(args.mine), _load_json(args.available))
        else:  # stdin 模式
            payload = json.load(sys.stdin)
            t = payload.pop("task")
            out = {
                "redeem": lambda: plan_redemption(
                    payload["points"], payload.get("expiring", 0), payload["products"], payload.get("deadline_days", 14)
                ),
                "lottery": lambda: lottery_ev(payload["info"]),
                "coupon": lambda: coupon_radar(payload["mine"], payload["available"]),
            }[t]()
    except KeyError as e:
        out = {"error": f"缺少必要字段: {e}"}
    except Exception as e:  # noqa: BLE001
        out = {"error": f"{type(e).__name__}: {e}"}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
