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
import re
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


def _cash_from_name(name):
    """从商品/券名称内嵌面值解析现金价值，如「6.9元可乐麦炫酷」→ 6.9。"""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*元", str(name))
    return float(m.group(1)) if m else 0.0


def _norm_products(raw, now=None):
    """归一化 mall-points-products / mall-product-detail 的返回。

    实测麦当劳 MCP 字段（2026-10）：`spuId`/`spuName`/`point`/`price`/`status`/`downTime`，
    其中 `price` 对积分商品恒为 "0"（不可用），现金价值内嵌在 `spuName` 前缀；
    `status` 对已下架商品仍返回 2（不可信），下架判定以 `downTime` 为准。
    """
    now = now or datetime.now()
    items = raw if isinstance(raw, list) else raw.get("items") or raw.get("list") or raw.get("products") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        points = _clean_number(it.get("points", it.get("point", it.get("needPoint"))))
        name = it.get("spuName") or it.get("name") or it.get("title") or it.get("productName") or "未命名商品"
        # 显式现金价值字段优先（price 为 "0" 时忽略），否则从名称前缀解析
        cash = 0.0
        for k in ("cash_value", "cash", "price"):
            v = _clean_number(it.get(k))
            if v > 0:
                cash = v
                break
        if cash <= 0:
            cash = _cash_from_name(name)
        down = it.get("downTime") or it.get("down_time")
        if down:
            try:
                if datetime.strptime(str(down)[:19], "%Y-%m-%d %H:%M:%S") < now:
                    continue  # 已下架
            except ValueError:
                pass
        if points <= 0:
            continue
        out.append(
            {
                "id": it.get("spuId") or it.get("id") or it.get("productId") or it.get("code"),
                "name": name,
                "points": points,
                "cash_value": cash,
                "value_per_point": round(cash / points, 4),
                "down_time": down or "",
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


def _prize_face_value(pz, point_value=0.0, meal_price=30.0):
    """从奖品名称估计面值：立减X元券 / X折券 / N积分 / 名称前缀X元。未知返回 None。"""
    name = str(pz.get("name") or pz.get("prizeName") or "")
    m = re.search(r"立减\s*(\d+(?:\.\d+)?)\s*元", name)
    if m:
        return float(m.group(1))
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*元", name)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*折", name)
    if m:
        return round(meal_price * (1 - float(m.group(1)) / 10.0), 2)
    m = re.search(r"(\d+)\s*积分", name)
    if m and point_value > 0:
        return round(int(m.group(1)) * point_value, 2)
    return None


def lottery_ev(info, point_value=None, meal_price=30.0):
    """抽奖期望值 / 盈亏平衡分析。

    实测麦当劳 MCP 的 query-lottery-info **不返回中奖概率**（prizes 仅含 name/typeText），
    因此分两种模式：
    - 有概率数据 → 输出 EV 与结论；
    - 无概率数据 → 输出盈亏平衡敏感性表（官方未公开概率，不做伪 EV）。

    point_value：积分的现金锚点（元/分），来自积分体检的最优兑换性价比，如 0.138。
    """
    prizes = info.get("prizes") or info.get("prizeList") or info.get("activityPrizes") or []
    cost_points = _clean_number(
        info.get("cost_points", info.get("drawPoint", info.get("consumePoints", info.get("drawCostPoints")))),
        default=-1,
    )
    if not prizes or cost_points < 0:
        return {"error": "抽奖活动数据不完整（缺奖品列表或消耗规则）"}

    probs = [pz.get("probability", pz.get("rate", pz.get("winRate"))) for pz in prizes]
    has_probability = any(p is not None and _parse_probability(p) > 0 for p in probs)
    known_values = [v for v in (_prize_face_value(pz, point_value or 0, meal_price) for pz in prizes) if v is not None]

    # ── 模式 1：有概率 → 真 EV ────────────────────────────────────────────
    if has_probability:
        total_prob, ev_cash, table = 0.0, 0.0, []
        for pz in prizes:
            name = pz.get("name") or pz.get("prizeName") or "未知奖品"
            prob = _parse_probability(pz.get("probability", pz.get("rate", pz.get("winRate"))))
            cash = _clean_number(pz.get("cash_value", pz.get("price", pz.get("worth"))))
            if cash <= 0:
                cash = _prize_face_value(pz, point_value or 0, meal_price) or 0.0
            total_prob += prob
            ev_cash += prob * cash
            table.append(
                {"name": name, "probability": round(prob, 6), "cash_value": cash, "contribution": round(prob * cash, 4)}
            )
        anchor = point_value if point_value and point_value > 0 else 0.01
        cost_cash = cost_points * anchor
        ev_net = ev_cash - cost_cash
        advice = (
            "🎯 期望为正，长期看值得一抽（但单次方差极大，理性摸奖）"
            if ev_net > 0
            else "🧊 期望为负，把积分留着换商城商品更划算"
        )
        return {
            "mode": "ev",
            "draw_cost_points": cost_points,
            "draw_cost_cny_estimate": round(cost_cash, 2),
            "ev_gross_cny": round(ev_cash, 4),
            "ev_net_cny": round(ev_net, 4),
            "prize_table": sorted(table, key=lambda x: -x["probability"]),
            "probability_sum": round(total_prob, 6),
            "probability_note": (
                "中奖概率之和 < 1，差额为谢谢参与" if total_prob < 0.999 else "概率之和 = 1，人人有奖型抽奖"
            ),
            "advice": advice,
        }

    # ── 模式 2：无概率 → 盈亏平衡敏感性（诚实模式） ────────────────────────
    anchor = point_value if point_value and point_value > 0 else None
    if anchor is None:
        return {
            "mode": "insufficient_data",
            "error": "官方未公开中奖概率，且缺少积分现金锚点 point_value（元/分）；"
            "请先跑积分体检 redeem 拿到 value_per_point 再来",
            "draw_cost_points": cost_points,
            "prize_names": [pz.get("name") for pz in prizes],
        }
    cost_cash = cost_points * anchor
    breakeven = [
        {"win_rate": p, "required_avg_prize_value": round(cost_cash / p, 2)} for p in (0.1, 0.2, 0.5, 1.0)
    ]
    known_avg = round(sum(known_values) / len(known_values), 2) if known_values else None
    best_known = max(known_values) if known_values else None
    beat = known_avg is not None and known_avg > cost_cash
    return {
        "mode": "breakeven",
        "note": "官方接口未公开中奖概率，无法计算真实 EV；以下为盈亏平衡参考，不构成伪结论",
        "draw_cost_points": cost_points,
        "draw_cost_cny": round(cost_cash, 2),
        "point_value_anchor": anchor,
        "prize_count": len(prizes),
        "known_face_values": {
            "count": len(known_values),
            "avg": known_avg,
            "max": best_known,
            "unknown_note": f"{len(prizes) - len(known_values)} 个折扣类奖品面值依赖餐品价格假设（当前假设 {meal_price} 元）",
        },
        "breakeven_table": breakeven,
        "reality_check": (
            f"即使中奖率 100%，已知面值均价 {known_avg} 元仍低于单抽成本 {cost_cash:.2f} 元 → 🧊 不值得为抽奖消耗积分"
            if beat is False and known_avg is not None
            else f"已知面值均价 {known_avg} 元 > 单抽成本 {cost_cash:.2f} 元（中奖率 100% 口径），实际取决于真实中奖率"
        ),
        "advice": "官方未公开概率；若要玩，建议单次试水并设定止损，不连抽",
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

    l = sub.add_parser("lottery", help="抽奖期望值 / 盈亏平衡分析")
    l.add_argument("--info", required=True, help="query-lottery-info 返回的 JSON 文件")
    l.add_argument("--point-value", type=float, default=None, help="积分现金锚点(元/分)，来自 redeem 的 value_per_point")
    l.add_argument("--meal-price", type=float, default=30.0, help="折扣券面值估算用的餐品价格假设(元)")

    c = sub.add_parser("coupon", help="券情雷达")
    c.add_argument("--mine", required=True)
    c.add_argument("--available", required=True)

    sub.add_parser("-", help="stdin JSON 模式")

    args = ap.parse_args()
    try:
        if args.task == "redeem":
            out = plan_redemption(args.points, args.expiring, _load_json(args.products), args.deadline_days)
        elif args.task == "lottery":
            out = lottery_ev(_load_json(args.info), args.point_value, args.meal_price)
        elif args.task == "coupon":
            out = coupon_radar(_load_json(args.mine), _load_json(args.available))
        else:  # stdin 模式
            payload = json.load(sys.stdin)
            t = payload.pop("task")
            out = {
                "redeem": lambda: plan_redemption(
                    payload["points"], payload.get("expiring", 0), payload["products"], payload.get("deadline_days", 14)
                ),
                "lottery": lambda: lottery_ev(
                    payload["info"], payload.get("point_value"), payload.get("meal_price", 30.0)
                ),
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
