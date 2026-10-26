# -*- coding: utf-8 -*-
"""
生成《技术站列车编组计划》算例演示页 static/bianzu.html

计算口径（教材第十一章）：
  · 车站 i 的编组方案 = 该站出发车流的一个划分，每个分块开行一列流，
    列车终点 = 块内最近到站（下标最小者）；
  · 车流按「接续归并」走行：到站后在不越过目的地的前提下，乘终点最远的列流，
    每次换乘计一次改编；
  · F耗 = Σ N改编·t节 + Σ k_i·T集^i
    F节 = Σ N通·t节 − Σ k_i·T集^i = C − F耗。

脚本职责：
  1. 复算并断言 6 道题（例11.3、例11.5、例11.6、习题1–3）的教材结果；
  2. 调用 draw_scheme.build() 生成页面所需 SVG，写入 static/svg/bianzu/；
  3. 输出静态页 static/bianzu.html。

用法：
    venv/bin/python scripts/编组方案svg绘图/build_bianzu_page.py
"""

import os
import sys
from itertools import product

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
STATIC = os.path.join(ROOT, "static")
SVG_OUT = os.path.join(STATIC, "svg", "bianzu")

sys.path.insert(0, HERE)
import draw_scheme  # noqa: E402


# ============================================================ 一、计算内核
def partitions(items):
    """生成集合的全部划分（Bell 数）。"""
    items = list(items)
    if not items:
        yield []
        return
    first = items[0]
    for rest in partitions(items[1:]):
        yield [[first]] + [b[:] for b in rest]
        for k in range(len(rest)):
            new = [b[:] for b in rest]
            new[k] = [first] + new[k]
            yield new


def evaluate(n, flows, T, t, combo):
    """计算一个编组方案的改编、列流数与目标函数。

    combo[i]：车站 i 的车流划分（块内为去向站的下标）。
    返回 dict(cost, adapt, k, detail, through)。
    """
    endpoints = [set(min(b) for b in blocks) if blocks else set() for blocks in combo]
    k = [sum(1 for x in endpoints[i] if x > i + 1) for i in range(n)]
    adapt = 0
    detail = []
    through = set()
    for (name, i, j, N) in flows:
        block = next(b for b in combo[i] if j in b)
        e = min(block)
        while e < j:
            adapt += N * t[e]
            detail.append((name, i, j, e, N))
            e = max([x for x in endpoints[e] if x <= j] + [e + 1])
        for p in range(i + 1, j):
            if p not in [d[3] for d in detail if d[0] == name]:
                through.add((name, p))
    cost = adapt + sum(k[i] * T[i] for i in range(n))
    return {"cost": cost, "adapt": adapt, "k": k,
            "detail": detail, "through": through}


def through_sum(flows, t, through):
    val = 0
    by = {f[0]: f for f in flows}
    for (name, p) in through:
        val += by[name][3] * t[p]
    return val


def f_jie(n, flows, T, t, combo):
    ev = evaluate(n, flows, T, t, combo)
    train = sum(ev["k"][i] * T[i] for i in range(n))
    return through_sum(flows, t, ev["through"]) - train


def absolute_flows(n, flows, T, t):
    """满足绝对条件的车流：某中间站的通过节省已超过开一列流的集结消耗。"""
    out = set()
    for (name, i, j, N) in flows:
        if any(N * t[p] > T[i] for p in range(i + 1, j)):
            out.add(name)
    return out


def expr_label(combo, n):
    """把划分写成教材式「0+1,2; …」（站号）。"""
    out = []
    for blocks in combo:
        if not blocks:
            out.append("—")
            continue
        groups = []
        for b in blocks:
            nums = sorted(n - 1 - x for x in b)
            groups.append("+".join(str(x) for x in nums))
        groups.sort(key=lambda s: (int(s.split("+")[0]), len(s)), reverse=True)
        out.append(",".join(groups))
    return " ; ".join(out)


# ============================================================ 二、题目数据
def F(name, i, j, N):
    return (name, i, j, N)


PROBLEMS = [
    {
        "key": "ex11.3", "title": "例 11.3", "n": 4,
        "labels": ["A3", "A2", "A1", "A0"],
        "T": [500, 600, 0, 0], "t": {1: 4.0, 2: 3.0},
        "flows": [F("31", 0, 2, 120), F("30", 0, 3, 100), F("20", 1, 3, 80)],
        "note": "短途流 N32、N21、N10 未给车数，不参与目标函数计算。",
        "stages": [
            ("初始方案（方案⑦）", 7, "11.9.7", "方案⑦：A3 的 N30 单开，N31 与 N32 合开到 A2；A2 的 N20 与 N21 合开到 A1。", 200),
            ("调整方案 1（方案⑧，最优）", 8, "11.9.8", "N30 与 N31 合开到 A1：节省 N31 在 A2 的通过 480，损失 N30 在 A1 的改编 300，F节 200→380。", 380),
            ("调整方案 2（方案⑤）", 5, "11.9.5", "取消 3→1 列流节省 500，N30、N31 在 A2 改编损失 880；新开 2→0 列流增加 600，但 N20、N30 在 A1 通过节省 240+300，净 −440，F节=−60，不如方案⑧。", -60),
        ],
        "opt_stage": 1,
        "abs_expect": [1600, 1580, 1400, 1500, 1480, 1240, 1220, 1040, 1440, 1420],
        "abs_opt": 8,
        "prose_abs": "4 个支点站方向共 10 个编组方案。逐方案计算改编车小时与集结车小时，"
                     "方案⑧（0+1,2; 0+1; 0）的 F耗 最小，为 1040 车小时。",
        "prose_table": "N31·t₂=480＜T₃=500、N30·t₁=300＜T₃=500、N20·t₁=240＜T₂=600，"
                       "均不满足绝对条件；N30·(t₂+t₁)=700＞T₃=500，满足必要条件，暂定单开。"
                       "初始方案即方案⑦（F节=200）。调整 1：N30 与 N31 合开到 A1，净节省 180，F节=380；"
                       "调整 2：N30 与 N20 在 A2 合并，F节=−60。故方案⑧最优。",
        "conclusion": "方案⑧：A3 的 N30 与 N31 合开到 A1、N32 单开；A2 的 N20 与 N21 合开到 A1；A1 的 N10 开往 A0。",
        "obj": "F耗 = 1040 车小时；F节 = 380 车小时",
        "combo_name": "4",
    },
    {
        "key": "ex11.5", "title": "例 11.5", "n": 4,
        "labels": ["A3", "A2", "A1", "A0"],
        "T": [500, 540, 0, 0], "t": {1: 4.0, 2: 3.0},
        "flows": [F("31", 0, 2, 95), F("30", 0, 3, 115), F("20", 1, 3, 185)],
        "note": "短途流 N32=100、N21=90、N10=120 只影响图形，不进入目标函数。",
        "stages": [
            ("初始方案（方案②）", 2, "11.9.2", "N30 单开 3→0，N31 与 N32 合开到 A2；N20 单开 2→0，N21 与 N31 合开到 A1。F节=320。", 320),
            ("过渡方案Ⅰ（方案③）", 3, "11.9.3", "N30 与 N31 合开到 A1：节省 N31 的 380，损失 N30 在 A1 的 345，净节省 35。F节=355。", 355),
            ("过渡方案Ⅱ（方案⑤，最优）", 5, "11.9.5", "N30 改在 A2 与 N20 合并：损失 N30 在 A2 的 460，节省 3→0 列流 500，净节省 40。F节=360。", 360),
        ],
        "opt_stage": 2,
        "abs_expect": [1540, 1420, 1385, 1500, 1380, 1555, 1435, 1400, 1860, 1740],
        "abs_opt": 5,
        "prose_abs": "逐方案计算后，方案⑤（0+1+2; 0+1; 0）的 F耗 最小，为 1380 车小时。",
        "prose_table": "N20·t₁=555＞T₂=540，满足绝对条件，必须单开（△）；"
                       "N30·(t₂+t₁)=805＞T₃=500，满足必要条件，暂定单开（○）；"
                       "N31·t₂=380＜T₃=500，不满足，与 N32 一起经 A2 转接。初始方案 F节=320。"
                       "过渡Ⅰ（N30 与 N31 合并）F节=355；过渡Ⅱ（N30 与 N20 在 A2 合并）F节=360，优于过渡Ⅰ，故选过渡Ⅱ。",
        "conclusion": "方案⑤：A3 的 N30、N31、N32 全部经 A2 转接；A2 的 N20 单开 2→0，N21 与 N31 开往 A1；A1 的 N10 开往 A0。",
        "obj": "F耗 = 1380 车小时；F节 = 360 车小时",
        "combo_name": "4",
    },
    {
        "key": "ex11.6", "title": "例 11.6", "n": 5,
        "labels": ["A4", "A3", "A2", "A1", "A0"],
        "T": [600, 550, 500, 0, 0], "t": {1: 2.5, 2: 3.0, 3: 2.0},
        "flows": [F("42", 0, 2, 180), F("41", 0, 3, 250), F("40", 0, 4, 60),
                  F("31", 1, 3, 100), F("30", 1, 4, 130), F("20", 2, 4, 300)],
        "note": "短途流 N43、N32、N21、N10 未给车数，只影响图形。",
        "stages": [
            ("初始方案", 0, "11.20", "N41 单开 4→1；N42 与 N40 合开到 A2；N30 单开 3→0；N20 在 A2 接续 N40 开往 A0。F节=1095。", 1095),
            ("过渡方案Ⅰ", 1, "11.21", "N40 改与 N41 合并到 A1：取消 4→2 列流节省 600，N40 在 A2 由改编改为通过节省 180，在 A1 改编损失 120，N42 在 A3 改编损失 450，净节省 210。F节=1305。", 1305),
            ("过渡方案Ⅱ", 2, "11.22", "N30 改与 N31 合并到 A1：节省 N31 在 A2 的 300，损失 N30 在 A1 的 260，净节省 40。F节=1345。", 1345),
            ("最佳方案", 3, "11.23", "N30 改为经 A2 与 N20 合并：取消 3→1 列流节省 550，N30 在 A2 改编损失 390、N31 在 A2 改编损失 300，N30 在 A1 由改编变为通过节省 260，净节省 120。F节=1465。", 1465),
        ],
        "opt_stage": 3,
        "abs_expect": None,
        "abs_opt": None,
        "prose_abs": None,
        "prose_table": "绝对条件：N41·t₃=625＞T₄=600、N20·t₁=600＞T₂=500，二者必须单开；"
                       "N30·(t₂+t₁)=650＞T₃=550，满足必要条件，暂定单开。其余车流先合并：N42 与 N40 合开到 A2。"
                       "在此基础上依次压缩 N40、N30 的到站/发站，得到过渡Ⅰ、Ⅱ，最后 N30 与 N20 在 A2 合并，F节=1465。",
        "conclusion": "A4 的 N40+N41 开往 A1、N42 经 A3 转接；A3 全部车流经 A2 转接；"
                      "A2 的 N20 吸收 N30 后单开 2→0，N21 与 N31 开往 A1；A1 的 N10 与 N40 开往 A0。",
        "obj": "F耗 = 2360 车小时；F节 = 1465 车小时",
        "combo_name": "5",
    },
    {
        "key": "xt1", "title": "习题 1", "n": 4,
        "labels": ["A3", "A2", "A1", "A0"],
        "T": [600, 500, 0, 0], "t": {1: 4.0, 2: 3.0},
        "flows": [F("31", 0, 2, 100), F("30", 0, 3, 100), F("20", 1, 3, 100)],
        "note": "短途流 N32=50、N21=200、N10=50 只影响图形。",
        "stages": [
            ("初始方案（方案⑦）", 7, "11.9.7", "N30 单开 3→0；N31 与 N32 合开到 A2；N20 与 N21 合开到 A1。F节=100。", 100),
            ("调整方案（方案⑧，最优）", 8, "11.9.8", "N30 与 N31 合开到 A1：节省 N31 在 A2 的 400，损失 N30 在 A1 的 300，净节省 100。F节=200。", 200),
        ],
        "opt_stage": 1,
        "abs_expect": [1700, 1500, 1400, 1500, 1300, 1500, 1300, 1200, 1600, 1400],
        "abs_opt": 8,
        "prose_abs": "逐方案计算，方案⑧（0+1,2; 0+1; 0）F耗 最小，为 1200 车小时。",
        "prose_table": "没有车流满足绝对条件；N30·(t₂+t₁)=700＞T₃=600，满足必要条件，暂定单开；"
                       "N31·t₂=400＜T₃、N20·t₁=300＜T₂，均不满足，先与相邻短途流合并。"
                       "初始方案为方案⑦，F节=100。将 N30 与 N31 合开到 A1 后，F节=200，为最优；"
                       "若 N30 改与 N20 在 A2 合并（方案⑤），F节=100，没有改善。",
        "conclusion": "方案⑧：A3 的 N30 与 N31 合开到 A1、N32 单开；A2 的 N20 与 N21 合开到 A1；A1 的 N10 开往 A0。",
        "obj": "F耗 = 1200 车小时；F节 = 200 车小时",
        "combo_name": "4",
    },
    {
        "key": "xt2", "title": "习题 2", "n": 5,
        "labels": ["A4", "A3", "A2", "A1", "A0"],
        "T": [600, 600, 500, 0, 0], "t": {1: 5.0, 2: 5.0, 3: 4.0},
        "flows": [F("42", 0, 2, 170), F("41", 0, 3, 100), F("40", 0, 4, 360),
                  F("31", 1, 3, 20), F("30", 1, 4, 150), F("20", 2, 4, 200)],
        "note": "短途流 N43、N32、N21、N10 均为 0（表中以“—”表示）。",
        "stages": [
            ("初始方案", 0, None, "N42、N41、N40 在 A4 分别单开；N30 单开 3→0；N20 单开 2→0；N31 经 A2 转接。F耗=3000。", 6140),
            ("调整方案（最优）", 1, "xt2", "N41 并入 4→2 的列流：取消 4→1 列流节省 600，N41 改在 A2 改编损失 500，净节省 100。F耗=2900。", 6240),
        ],
        "opt_stage": 1,
        "abs_expect": None,
        "abs_opt": None,
        "prose_abs": None,
        "prose_table": "绝对条件：N42·t₃=850＞T₄、N40·t₃=1800＞T₄、N30·t₂=750＞T₃、N20·t₁=800＞T₂，"
                       "四支车流必须单开；N41·(t₃+t₂)=1000＞T₄，满足必要条件，暂定单开；N31 不满足。"
                       "初始方案 F耗=3000、F节=6140。把 N41 并入 N42 的 4→2 列流后，取消一列 4→1，"
                       "净节省 100，F耗=2900、F节=6240，为全枚举 150 个方案中的最小值。",
        "conclusion": "A4 的 N40 单开 4→0，N41+N42 合并开往 A2；A3 的 N30 单开 3→0，N31 经 A2 转接；"
                      "A2 的 N20 单开 2→0，N21 与 N41、N31 开往 A1；A1 的 N10 开往 A0。",
        "obj": "F耗 = 2900 车小时；F节 = 6240 车小时",
        "combo_name": "5",
    },
    {
        "key": "xt3", "title": "习题 3", "n": 5,
        "labels": ["A4", "A3", "A2", "A1", "A0"],
        "T": [560, 560, 560, 0, 0], "t": {1: 3.5, 2: 2.6, 3: 3.1},
        "flows": [F("42", 0, 2, 580), F("41", 0, 3, 90), F("40", 0, 4, 200),
                  F("31", 1, 3, 20), F("30", 1, 4, 130), F("20", 2, 4, 300)],
        "note": "短途流 N43、N32、N21、N10 均为 0。",
        "stages": [
            ("初始方案", 0, None, "N42 单开 4→2、N40 单开 4→0、N41 并入 4→2 列流；N30 单开 3→0；N20 单开 2→0。F耗=2526。", 3616),
            ("调整方案 1", 1, None, "N40 改并入 4→2 列流：取消 4→0 列流节省 560，N40 在 A2 改编损失 520，净节省 40。F耗=2486。", 3656),
            ("调整方案 2（最优）", 2, "xt3", "N30 不再单开 3→0，改经 3→2 在 A2 与 N20 合并：取消 3→0 列流节省 560，N30 在 A2 改编损失 338，净节省 222。F耗=2264。", 3878),
        ],
        "opt_stage": 2,
        "abs_expect": None,
        "abs_opt": None,
        "prose_abs": None,
        "prose_table": "绝对条件：N42·t₃=2030＞T₄、N40·t₃=700＞T₄、N20·t₁=930＞T₂，必须单开；"
                       "N30·(t₂+t₁)=741＞T₃，满足必要条件；N41·(t₃+t₂)=549＜T₄（仅差 11），不满足，与 N42 合并到 A2。"
                       "初始方案 F耗=2526、F节=3616。调整 1 把 N40 并入 4→2 列流（+40）；"
                       "调整 2 把 N30 改为经 A2 与 N20 合并（+222），得到 F耗=2264、F节=3878 的最优方案。",
        "conclusion": "A4 的 N40+N41+N42 合并开往 A2；A3 全部车流经 A2 转接；"
                      "A2 的 N20 吸收 N30、N40 后单开 2→0，N21 与 N41、N31 开往 A1；A1 的 N10 开往 A0。",
        "obj": "F耗 = 2264 车小时；F节 = 3878 车小时",
        "combo_name": "5",
    },
]


# ============================================================ 三、方案组合
# 4 站：A3 的 5 种划分 × A2 的 2 种划分，教材顺序
P4_A3 = {
    "sep": [[1], [2], [3]],      # 0,1,2
    "m12": [[1, 2], [3]],        # 0,1+2
    "m01": [[1], [2, 3]],        # 0+1,2
    "m02": [[1, 3], [2]],        # 0+2,1
    "all": [[1, 2, 3]],          # 0+1+2
}
P4_A2 = {"sep": [[2], [3]], "all": [[2, 3]]}
P4_TAIL = ([[3]], [])
P4_ORDER = [
    ("sep", "sep", "0,1,2; 0,1; 0"),
    ("m12", "sep", "0,1+2; 0,1; 0"),
    ("m01", "sep", "0+1,2; 0,1; 0"),
    ("m02", "sep", "0+2,1; 0,1; 0"),
    ("all", "sep", "0+1+2; 0,1; 0"),
    ("sep", "all", "0,1,2; 0+1; 0"),
    ("m12", "all", "0,1+2; 0+1; 0"),
    ("m01", "all", "0+1,2; 0+1; 0"),
    ("m02", "all", "0+2,1; 0+1; 0"),
    ("all", "all", "0+1+2; 0+1; 0"),
]


def combo4(a3, a2):
    return (P4_A3[a3], P4_A2[a2], P4_TAIL[0], P4_TAIL[1])


# 5 站：各题各阶段的划分（0=A4 … 4=A0）
C = lambda *blocks: [list(b) for b in blocks]
P5 = {
    "ex11.6": {
        0: (C((1,), (2, 4), (3,)), C((2, 3), (4,)), C((3,), (4,)), C((4,)), []),
        1: (C((1, 2), (3, 4)), C((2, 3), (4,)), C((3,), (4,)), C((4,)), []),
        2: (C((1, 2), (3, 4)), C((2,), (3, 4)), C((3,), (4,)), C((4,)), []),
        3: (C((1, 2), (3, 4)), C((2, 3, 4)), C((3,), (4,)), C((4,)), []),
    },
    "xt2": {
        0: (C((1,), (2,), (3,), (4,)), C((2, 3), (4,)), C((3,), (4,)), C((4,)), []),
        1: (C((1,), (2, 3), (4,)), C((2, 3), (4,)), C((3,), (4,)), C((4,)), []),
    },
    "xt3": {
        0: (C((1,), (2, 3), (4,)), C((2, 3), (4,)), C((3,), (4,)), C((4,)), []),
        1: (C((1,), (2, 3, 4)), C((2, 3), (4,)), C((3,), (4,)), C((4,)), []),
        2: (C((1,), (2, 3, 4)), C((2, 3, 4)), C((3,), (4,)), C((4,)), []),
    },
}

# 5 站初始/过渡方案表达式（用于页面标题）
P5_EXPR = {
    ("ex11.6", 0): "0+2,1,3; 0,1+2; 0,1; 0",
    ("ex11.6", 1): "0+1,2+3; 0,1+2; 0,1; 0",
    ("ex11.6", 2): "0+1,2+3; 0+1,2; 0,1; 0",
    ("ex11.6", 3): "0+1,2+3; 0+1+2; 0,1; 0",
    ("xt2", 0): "0,1,2,3; 0,1+2; 0,1; 0",
    ("xt2", 1): "0,1+2,3; 0,1+2; 0,1; 0",
    ("xt3", 0): "0,1+2,3; 0,1+2; 0,1; 0",
    ("xt3", 1): "0+1+2,3; 0,1+2; 0,1; 0",
    ("xt3", 2): "0+1+2,3; 0+1+2; 0,1; 0",
}


def stage_combo(p, idx):
    if p["combo_name"] == "4":
        scheme_no = p["stages"][idx][1]
        return combo4(*P4_ORDER[scheme_no - 1][:2])
    return P5[p["key"]][idx]


def stage_expr(p, idx):
    if p["combo_name"] == "4":
        return P4_ORDER[p["stages"][idx][1] - 1][2]
    return P5_EXPR[(p["key"], idx)]


# ============================================================ 四、HTML 构件
def N(name):
    return f'N<sub>{name}</sub>'


def data_table(p):
    n = p["n"]
    head = "".join(f"<th>{s}</th>" for s in p["labels"])
    T_cells = "".join(f"<td>{p['T'][i] if p['T'][i] else ''}</td>" for i in range(n))
    t_cells = "".join(f"<td>{p['t'][i] if i in p['t'] else ''}</td>" for i in range(n))
    main = (f"<div class='table-scroll'><table class='plan-table'>"
            f"<thead><tr><th>项目</th>{head}</tr></thead><tbody>"
            f"<tr><td class='lbl'>T<sub>集</sub></td>{T_cells}</tr>"
            f"<tr><td class='lbl'>t<sub>节</sub></td>{t_cells}</tr>"
            f"</tbody></table></div>")
    flow_rows = "".join(
        f"<tr><td class='lbl'>{N(name)}</td>"
        f"<td>{p['labels'][i]} → {p['labels'][j]}</td><td>{q}</td></tr>"
        for (name, i, j, q) in p["flows"])
    flows = (f"<div class='table-scroll'><table class='plan-table'>"
             f"<thead><tr><th>车流</th><th>径路</th><th>车数</th></tr></thead>"
             f"<tbody>{flow_rows}</tbody></table></div>")
    return main + flows


def abs_table(p):
    n = p["n"]
    flows = p["flows"]
    rows = []
    best_cost = None
    best_idx = None
    vals = []
    for k, (a3, a2, expr) in enumerate(P4_ORDER, 1):
        combo = combo4(a3, a2)
        ev = evaluate(n, flows, p["T"], p["t"], combo)
        vals.append((k, expr, combo, ev))
    best_cost = min(v["cost"] for _, _, _, v in vals)
    for (k, expr, combo, ev) in vals:
        adapted = {}
        for (name, i, j, e, q) in ev["detail"]:
            adapted[(name, e)] = adapted.get((name, e), 0) + q
        cells = [
            adapted.get(("31", 1), 0),
            adapted.get(("30", 1), 0),
            adapted.get(("30", 2), 0),
            adapted.get(("20", 2), 0),
        ]
        tr = ["<tr" + (" class='opt'" if ev["cost"] == best_cost else "") + ">"]
        tr.append(f"<td>{'①②③④⑤⑥⑦⑧⑨⑩'[k-1]}</td><td class='lbl'>{expr}</td>")
        tr.append("".join(f"<td>{c}</td>" for c in cells))
        tr.append(f"<td>{ev['adapt']:.0f}</td>")
        tr.append(f"<td>{ev['k'][0]*p['T'][0]:.0f}</td>")
        tr.append(f"<td>{ev['k'][1]*p['T'][1]:.0f}</td>")
        tr.append(f"<td><strong>{ev['cost']:.0f}</strong></td></tr>")
        rows.append("".join(tr))
    head = ("<tr><th>方案</th><th>编组方案</th><th>N31@A2</th><th>N30@A2</th>"
            "<th>N30@A1</th><th>N20@A1</th><th>N改编·t节</th><th>k₃·T₃</th><th>k₂·T₂</th><th>F耗</th></tr>")
    return (f"<div class='table-scroll'><table class='plan-table'><thead>{head}</thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>"
            f"<p class='note'>表中 N31@A2 等为在该站改编的车数（0 表示无改编通过）；"
            f"k₃、k₂ 为该站开行的非短途直达列流数。最优行已高亮。</p>")


def stage_table(p, idx):
    n = p["n"]
    combo = stage_combo(p, idx)
    flows = p["flows"]
    T, t = p["T"], p["t"]
    ev = evaluate(n, flows, T, t, combo)
    abs_set = absolute_flows(n, flows, T, t)
    # 逐流按站填格
    flow_rows = []
    for (name, i, j, q) in flows:
        cells = []
        last_inter = j - 1
        for k in range(n):
            if k == i:
                cells.append("<td>—</td>")
            elif i < k < j:
                val = q * t[k]
                if (name, k) in ev["through"]:
                    mark = "△" if (name in abs_set and k == last_inter) else "○"
                    cls = "mark-t" if mark == "△" else "mark-o"
                    cells.append(f"<td>{val:.0f}<span class='{cls}'>{mark}</span></td>")
                else:
                    cells.append(f"<td class='muted'>{val:.0f}</td>")
            else:
                cells.append("<td></td>")
        flow_rows.append(f"<tr><td class='lbl'>{N(name)}={q}</td>{''.join(cells)}</tr>")
    # 各站改编车数与改编车小时
    adapt_by = {}
    for (name, i, j, e, q) in ev["detail"]:
        adapt_by[e] = adapt_by.get(e, 0) + q
    row_na = ["<tr><td class='lbl'>N<sub>改编</sub></td>"]
    row_nt = ["<tr><td class='lbl'>N<sub>改编</sub>·t<sub>节</sub></td>"]
    for k in range(n):
        if k in adapt_by:
            row_na.append(f"<td>{adapt_by[k]}</td>")
            row_nt.append(f"<td>{adapt_by[k] * t[k]:.0f}</td>")
        else:
            row_na.append("<td></td>")
            row_nt.append("<td></td>")
    row_na.append("</tr>")
    row_nt.append(f"<td><strong>{ev['adapt']:.0f}</strong></td></tr>")
    # 列流数
    row_k = ["<tr><td class='lbl'>k<sub>i</sub>（非短途直达列流数）</td>"]
    row_kt = ["<tr><td class='lbl'>k<sub>i</sub>·T<sub>集</sub><sup>i</sup></td>"]
    for i in range(n):
        if i < n - 1 and T[i]:
            row_k.append(f"<td>{ev['k'][i]}</td>")
            row_kt.append(f"<td>{ev['k'][i] * T[i]:.0f}</td>")
        else:
            row_k.append("<td></td>")
            row_kt.append("<td></td>")
    row_k.append("</tr>")
    row_kt.append(f"<td><strong>{sum(ev['k'][i] * T[i] for i in range(n)):.0f}</strong></td></tr>")
    ts = through_sum(flows, t, ev["through"])
    train = sum(ev["k"][i] * T[i] for i in range(n))
    fj = ts - train
    head = "".join(f"<th>{s}</th>" for s in p["labels"])
    rows = ("".join(flow_rows) +
            "".join(row_na) + "".join(row_nt) +
            "".join(row_k) + "".join(row_kt) +
            f"<tr><td class='lbl'>ΣN<sub>通</sub>·t<sub>节</sub></td>"
            + "<td colspan='%d'><strong>%s</strong></td></tr>" % (n, f"{ts:.0f}") +
            f"<tr><td class='lbl'>F<sub>节</sub></td>"
            + "<td colspan='%d'><strong>%s</strong></td></tr>" % (n, f"{fj:.0f}"))
    html = (f"<div class='table-scroll'><table class='plan-table'>"
            f"<thead><tr><th>车流 / 项目</th>{head}</tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")
    return html, ev, fj


def figure(img, caption):
    return (f"<div class='figure'><img src='svg/bianzu/{img}.svg' alt='{caption}'>"
            f"<div class='figcap'>{caption}</div></div>")


# ============================================================ 五、组装页面
CSS = """
.nav-links{display:flex;gap:16px;justify-content:center;flex-wrap:wrap;margin:0 0 14px;font-size:14px}
.nav-links a{color:#1890ff;text-decoration:none}
.nav-links a:hover{text-decoration:underline}
.toc{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.toc a{background:#eef4ff;color:#1d63b8;border-radius:14px;padding:3px 11px;font-size:13px;text-decoration:none}
.toc a:hover{background:#dbe9ff}
.plan-table{border-collapse:collapse;width:100%;margin:10px 0 4px;font-size:13px}
.plan-table th,.plan-table td{border:1px solid #dcdfe6;padding:5px 7px;text-align:center;vertical-align:middle}
.plan-table th{background:#f5f7fa;font-weight:600;white-space:nowrap}
.plan-table td.lbl{text-align:left;white-space:nowrap}
.plan-table td.muted{color:#999}
.plan-table tr.opt td{background:#fff7e6}
.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.figure{text-align:center;margin:14px 0 6px}
.figure img{max-width:100%;height:auto;background:#fff;border:1px solid #eee;border-radius:4px;padding:6px}
.figcap{color:#666;font-size:13px;margin-top:4px;text-align:center}
.result-box{border-left:4px solid #1890ff;background:#f0f7ff;padding:10px 14px;border-radius:4px;margin-top:12px;font-size:14px}
.result-box strong{color:#0b4f9e}
.note{color:#666;font-size:13px;margin:6px 0}
.legend{font-size:13px;color:#555;margin:4px 0 0}
.mark-o{color:#1d7a46;margin-left:1px}
.mark-t{color:#b26a00;margin-left:1px;font-weight:700}
.stage-block{margin:14px 0}
.stage-block h4{font-size:14px;color:#1a1a2e;margin:10px 0 4px}
details.stage{border:1px solid #eee;border-radius:6px;padding:0 12px;margin:10px 0}
details.stage>summary{cursor:pointer;padding:9px 0;font-weight:600;color:#1a1a2e}
details.stage[open]>summary{margin-bottom:2px}
.formula{background:#fafafa;border:1px solid #eee;border-radius:4px;padding:8px 12px;margin:8px 0;font-size:15px}
.formula em{font-style:italic;font-family:"Times New Roman",serif}
.problem-statement{font-size:14px;color:#444}
.problem-statement b{color:#1a1a2e}
@media (max-width:600px){.plan-table{font-size:12px}.plan-table th,.plan-table td{padding:3px 4px}.card{padding:16px}}
"""


def section(p):
    n = p["n"]
    out = [f"<section class='card' id='{p['key']}'>",
           f"<h2>{p['title']} · {n} 个支点站（{p['labels'][0]}–{p['labels'][-1]}）</h2>",
           f"<p class='problem-statement'>{p['note']}</p>",
           "<h3>计算资料</h3>", data_table(p)]
    if p["abs_expect"]:
        out += ["<h3>绝对计算法</h3>", f"<p>{p['prose_abs']}</p>", abs_table(p)]
    out += ["<h3>表格计算法</h3>", f"<p>{p['prose_table']}</p>",
            "<p class='legend'>记号：○ 无改编通过（节省）；△ 满足绝对条件、开行直达列车；无记号 = 在该站改编。</p>"]
    for idx, (label, src_idx, img, desc, expect_fj) in enumerate(p["stages"]):
        table, ev, fj = stage_table(p, idx)
        assert abs(fj - expect_fj) < 1e-6, (p["key"], idx, fj, expect_fj)
        expr = stage_expr(p, idx)
        head = f"<h4>{label}（{expr}）</h4><p class='note'>{desc}</p>"
        body = table + (figure(img, f"{p['title']} · {label}") if img else "")
        if idx in (0, p["opt_stage"]):
            out.append(f"<div class='stage-block'>{head}{body}</div>")
        else:
            out.append(f"<details class='stage'><summary>{label}（{expr}） · 展开表格与到达站图</summary>{body}</details>")
    out += ["<h3>结论</h3>",
            f"<div class='result-box'><p><strong>最优方案：</strong>{p['conclusion']}</p>"
            f"<p><strong>目标函数值：</strong>{p['obj']}（F节 为相对全改编基线的节省）</p></div>",
            "</section>"]
    return "\n".join(out)


def build():
    # ---- 断言与最优校验 ----
    for p in PROBLEMS:
        n = p["n"]
        if p["combo_name"] == "4":
            got = []
            for (a3, a2, _) in P4_ORDER:
                ev = evaluate(n, p["flows"], p["T"], p["t"], combo4(a3, a2))
                got.append(ev["cost"])
            assert got == p["abs_expect"], (p["key"], got)
            assert got[p["abs_opt"] - 1] == min(got)
        else:
            dests = [[j for j in range(i + 1, n)] for i in range(n)]
            allp = [list(partitions(d)) if d else [[]] for d in dests]
            best = min(evaluate(n, p["flows"], p["T"], p["t"], c)["cost"]
                       for c in product(*allp))
            last = p["stages"][p["opt_stage"]]
            combo = stage_combo(p, p["opt_stage"])
            ev = evaluate(n, p["flows"], p["T"], p["t"], combo)
            assert abs(best - ev["cost"]) < 1e-6, (p["key"], best, ev["cost"])
        # 各阶段 F节 断言在 section() 内完成

    # ---- 生成 SVG ----
    os.makedirs(SVG_OUT, exist_ok=True)
    needed = {img for p in PROBLEMS for (_, _, img, _, _) in p["stages"] if img}
    schemes = {s["name"]: s for s in draw_scheme.SCHEMES}
    for name in sorted(needed):
        assert name in schemes, f"draw_scheme.SCHEMES 缺少 {name}"
        svg = draw_scheme.build(schemes[name])
        with open(os.path.join(SVG_OUT, f"{name}.svg"), "w", encoding="utf-8") as f:
            f.write(svg)

    # ---- HTML ----
    body = "\n".join(section(p) for p in PROBLEMS)
    toc = "".join(f"<a href='#{p['key']}'>{p['title']}</a>" for p in PROBLEMS)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>技术站列车编组计划 · 算例演示</title>
<link rel="stylesheet" href="style.css">
<style>{CSS}</style>
</head>
<body>
<div class="container">
<header>
  <h1>技术站列车编组计划 · 算例演示</h1>
  <p class="subtitle">绝对计算法 / 表格计算法 · 3 道例题 + 3 道习题 · 列车到达站图与最优方案</p>
</header>
<nav class="nav-links">
  <a href="/">调车作业计划</a>
  <a href="/bianzu">编组计划算例</a>
  <a href="/qa">教材问答</a>
</nav>
<main>
<section class="card" id="method">
  <h2>方法要点</h2>
  <p>每个支点站把本站出发的车流划分为若干组，每组开行一列流，列车到达该组内最近的车站；
  车流在途中按「接续归并」原则换乘：在不越过目的地的列流中，选择终点最远的一列。</p>
  <div class="formula">
    <div><em>F</em><sub>耗</sub> = Σ <em>N</em><sub>改编</sub> · <em>t</em><sub>节</sub> + Σ <em>k</em><sub>i</sub> · <em>T</em><sub>集</sub><sup>i</sup></div>
    <div><em>F</em><sub>节</sub> = Σ <em>N</em><sub>通</sub> · <em>t</em><sub>节</sub> − Σ <em>k</em><sub>i</sub> · <em>T</em><sub>集</sub><sup>i</sup> = <em>C</em> − <em>F</em><sub>耗</sub></div>
  </div>
  <p><b>绝对条件：</b>若某支车流在途中某站无改编通过的节省 <em>N</em><sub>ij</sub>·<em>t</em><sub>k</sub>
  已大于开行一列流在始发站的集结消耗 <em>T</em><sub>i</sub>，则该车流必须单开直达（△）。</p>
  <p><b>必要条件：</b>若 <em>N</em><sub>ij</sub>·Σ<em>t</em><sub>k</sub> &gt; <em>T</em><sub>i</sub>，暂定单开（○）。</p>
  <p><b>绝对计算法：</b>枚举全部编组方案，逐方案计算 <em>F</em><sub>耗</sub>，取最小者。<br>
  <b>表格计算法：</b>由绝对/必要条件确定初始方案，再按「压缩长程车流的到站或发站」逐步调整，
  比较 <em>F</em><sub>节</sub>，取节省最大者。</p>
  <div class="toc">{toc}</div>
</section>
{body}
</main>
<footer>
  <p>技术站列车编组计划 · 教学演示</p>
  <p><a href="/" class="qa-link">← 调车作业计划</a></p>
</footer>
</div>
</body>
</html>
"""
    path = os.path.join(STATIC, "bianzu.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"生成 {path}")
    print(f"SVG {len(needed)} 个 -> {SVG_OUT}")


if __name__ == "__main__":
    build()
