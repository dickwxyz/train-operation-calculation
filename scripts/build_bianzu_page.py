# -*- coding: utf-8 -*-
"""
生成《技术站列车编组计划》算例演示页 static/bianzu.html

页面结构（index 式）：
  · 顶部选择表：6 道题的已知信息 + 「查看计算」按钮；
  · 点击后只显示该题的结果 panel，其余 hidden；
  · 每个 panel 内按算例集步骤给出：
      已知信息 → 绝对计算法（如有，10 个方案各一张完整表 + 到达站图）
               → 表格计算法（第 1–4 步，每阶段一张完整表 + 到达站图）
               → 结论。

计算口径（教材第十一章）：
  · 车站 i 的编组方案 = 该站出发车流的一个划分，每个分块开行一列流，
    列车终点 = 块内最近到站（下标最小者）；
  · 车流按「接续归并」走行：到站后在不越过目的地的前提下，乘终点最远的列流，
    每次换乘计一次改编；
  · F耗 = Σ N改编·t节 + Σ k_i·T集^i
    F节 = Σ N通·t节 − Σ k_i·T集^i = C − F耗。

用法：
    venv/bin/python scripts/build_bianzu_page.py
"""

import os
import sys
from itertools import product

HERE = os.path.dirname(os.path.abspath(__file__))          # scripts/
ROOT = os.path.dirname(HERE)                                # 项目根
DRAW_DIR = os.path.join(HERE, "编组方案svg绘图")
STATIC = os.path.join(ROOT, "static")
SVG_OUT = os.path.join(STATIC, "svg", "bianzu")

sys.path.insert(0, DRAW_DIR)
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
    """计算一个编组方案的改编、列流数与目标函数。"""
    endpoints = [set(min(b) for b in blocks) if blocks else set() for blocks in combo]
    k = [sum(1 for x in endpoints[i] if x > i + 1) for i in range(n)]
    adapt = 0
    detail = []
    through = set()
    for (name, i, j, N) in flows:
        block = next(b for b in combo[i] if j in b)
        e = min(block)
        adapted_here = []
        while e < j:
            adapt += N * t[e]
            detail.append((name, i, j, e, N))
            adapted_here.append(e)
            e = max([x for x in endpoints[e] if x <= j] + [e + 1])
        for p in range(i + 1, j):
            if p not in adapted_here:
                through.add((name, p))
    cost = adapt + sum(k[i] * T[i] for i in range(n))
    return {"cost": cost, "adapt": adapt, "k": k,
            "detail": detail, "through": through}


def through_sum(flows, t, through):
    by = {f[0]: f for f in flows}
    return sum(by[name][3] * t[p] for (name, p) in through)


def absolute_flows(n, flows, T, t):
    """绝对条件（11.11）：N_ij · min{t_k | k∈K} ≥ T集^i。"""
    out = set()
    for (name, i, j, N) in flows:
        vals = [N * t[p] for p in range(i + 1, j)]
        if vals and min(vals) >= T[i]:
            out.add(name)
    return out


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
        "abs_method": True, "combo_name": "4",
        "abs_expect": [1600, 1580, 1400, 1500, 1480, 1240, 1220, 1040, 1440, 1420],
        "abs_opt": 8,
        "stages": [
            {"title": "初始方案（方案⑦）", "scheme": 7, "img": "11.9.7",
             "desc": "N30 单开 3→0；N31 与 N32 合开到 A2；N20 与 N21 合开到 A1。",
             "check": "", "expect_fj": 200, "expect_cost": 1220, "opt": False},
            {"title": "调整方案 1（方案⑧，最优）", "scheme": 8, "img": "11.9.8",
             "desc": "压缩 N30 的到站：N30 与 N31 合开到 A1。节省 N31 在 A2 的通过 480，"
                     "损失 N30 在 A1 的改编 300，净节省 180。",
             "check": "经验证，N30 在 A1 的通过节省 300＜T集³=500，不满足绝对条件，可以与 N31 合并。",
             "expect_fj": 380, "expect_cost": 1040, "opt": True},
            {"title": "调整方案 2（方案⑤）", "scheme": 5, "img": "11.9.5",
             "desc": "压缩 N30 的发站：N30 改经 A2 与 N20 合并。取消 3→1 列流节省 500，"
                     "N30、N31 在 A2 改编损失 880；新开 2→0 列流增加 600，"
                     "但 N20、N30 在 A1 通过节省 240+300，净 −440。",
             "check": "经验证，N30 在 A2 的通过节省 400＜T集²=600，不满足绝对条件，可以与 N20 合并。",
             "expect_fj": -60, "expect_cost": 1480, "opt": False},
        ],
        "merge_text": "N31 与 N32 合开到 A2；N20 与 N21 合开到 A1；N31 与 N20 无法合并，"
                      "形成不了非短途直达列流。初始方案为方案⑦。",
        "final_text": "三个方案的 F节 分别为 200、380、−60，调整方案 1（方案⑧）最大，故为最佳方案。",
        "conclusion": "方案⑧：A3 的 N30 与 N31 合开到 A1、N32 单开；A2 的 N20 与 N21 合开到 A1；"
                      "A1 的 N10 开往 A0。",
        "obj": "F耗 = 1040 车小时；F节 = 380 车小时",
    },
    {
        "key": "ex11.5", "title": "例 11.5", "n": 4,
        "labels": ["A3", "A2", "A1", "A0"],
        "T": [500, 540, 0, 0], "t": {1: 4.0, 2: 3.0},
        "flows": [F("31", 0, 2, 95), F("30", 0, 3, 115), F("20", 1, 3, 185)],
        "note": "短途流 N32=100、N21=90、N10=120 只影响图形，不进入目标函数。",
        "abs_method": True, "combo_name": "4",
        "abs_expect": [1540, 1420, 1385, 1500, 1380, 1555, 1435, 1400, 1860, 1740],
        "abs_opt": 5,
        "stages": [
            {"title": "初始方案（方案②）", "scheme": 2, "img": "11.9.2",
             "desc": "N30 单开 3→0；N31 与 N32 合开到 A2；N20 单开 2→0；N21 与 N31 合开到 A1。",
             "check": "", "expect_fj": 320, "expect_cost": 1420, "opt": False},
            {"title": "过渡方案Ⅰ（方案③）", "scheme": 3, "img": "11.9.3",
             "desc": "压缩 N30 的到站：N30 与 N31 合开到 A1。节省 N31 的 380，"
                     "损失 N30 在 A1 的 345，净节省 35。",
             "check": "", "expect_fj": 355, "expect_cost": 1385, "opt": False},
            {"title": "过渡方案Ⅱ（方案⑤，最优）", "scheme": 5, "img": "11.9.5",
             "desc": "压缩 N30 的发站：N30 在 A2 与 N20 合并。损失 N30 在 A2 的 460，"
                     "节省 3→0 列流 500，净节省 40。",
             "check": "", "expect_fj": 360, "expect_cost": 1380, "opt": True},
        ],
        "merge_text": "N31 与 N32 合开到 A2，N31 再与 N21 合开到 A1；N20 单开 2→0。"
                      "初始方案为方案②。",
        "final_text": "过渡方案Ⅱ 的 F节=360 大于过渡方案Ⅰ 的 355 和初始方案的 320，"
                      "故方案⑤为最佳方案。",
        "conclusion": "方案⑤：A3 的 N30、N31、N32 全部经 A2 转接；A2 的 N20 单开 2→0，"
                      "N21 与 N31 开往 A1；A1 的 N10 开往 A0。",
        "obj": "F耗 = 1380 车小时；F节 = 360 车小时",
    },
    {
        "key": "ex11.6", "title": "例 11.6", "n": 5,
        "labels": ["A4", "A3", "A2", "A1", "A0"],
        "T": [600, 550, 500, 0, 0], "t": {1: 2.5, 2: 3.0, 3: 2.0},
        "flows": [F("42", 0, 2, 180), F("41", 0, 3, 250), F("40", 0, 4, 60),
                  F("31", 1, 3, 100), F("30", 1, 4, 130), F("20", 2, 4, 300)],
        "note": "短途流 N43、N32、N21、N10 未给车数，只影响图形。",
        "abs_method": False, "combo_name": "5",
        "abs_expect": None, "abs_opt": None,
        "stages": [
            {"title": "初始方案", "combo_idx": 0, "img": "11.20",
             "desc": "N41 单开 4→1；N42 与 N40 合开到 A2；N30 单开 3→0；"
                     "N20 在 A2 接续 N40 开往 A0。",
             "check": "", "expect_fj": 1095, "expect_cost": 2730, "opt": False},
            {"title": "过渡方案Ⅰ", "combo_idx": 1, "img": "11.21",
             "desc": "压缩 N40 的到站：N40 改与 N41 合并到 A1。取消 4→2 列流节省 600，"
                     "N40 在 A2 由改编改为通过节省 180，在 A1 改编损失 120，"
                     "N42 在 A3 改编损失 450，净节省 210。",
             "check": "", "expect_fj": 1305, "expect_cost": 2520, "opt": False},
            {"title": "过渡方案Ⅱ", "combo_idx": 2, "img": "11.22",
             "desc": "压缩 N30 的到站：N30 改与 N31 合并到 A1。节省 N31 在 A2 的 300，"
                     "损失 N30 在 A1 的 260，净节省 40。",
             "check": "", "expect_fj": 1345, "expect_cost": 2480, "opt": False},
            {"title": "最佳方案", "combo_idx": 3, "img": "11.23",
             "desc": "压缩 N30 的发站：N30 改经 A2 与 N20 合并。取消 3→1 列流节省 550，"
                     "N30 在 A2 改编损失 390、N31 在 A2 改编损失 300，"
                     "N30 在 A1 由改编变为通过节省 260，净节省 120。",
             "check": "", "expect_fj": 1465, "expect_cost": 2360, "opt": True},
        ],
        "merge_text": "N42 与 N40 合开到 A2；N31 与 N32 经 A2 后与 N21 合开到 A1；"
                      "N30 单开 3→0；N20 在 A2 接续 N40 单开 2→0。初始方案见图 11.20。",
        "final_text": "四个阶段的 F节 依次为 1095、1305、1345、1465，最佳方案 F节=1465。",
        "conclusion": "A4 的 N40+N41 开往 A1、N42 经 A3 转接；A3 全部车流经 A2 转接；"
                      "A2 的 N20 吸收 N30 后单开 2→0，N21 与 N31 开往 A1；A1 的 N10 与 N40 开往 A0。",
        "obj": "F耗 = 2360 车小时；F节 = 1465 车小时",
    },
    {
        "key": "xt1", "title": "习题 1", "n": 4,
        "labels": ["A3", "A2", "A1", "A0"],
        "T": [600, 500, 0, 0], "t": {1: 4.0, 2: 3.0},
        "flows": [F("31", 0, 2, 100), F("30", 0, 3, 100), F("20", 1, 3, 100)],
        "note": "短途流 N32=50、N21=200、N10=50 只影响图形。",
        "abs_method": True, "combo_name": "4",
        "abs_expect": [1700, 1500, 1400, 1500, 1300, 1500, 1300, 1200, 1600, 1400],
        "abs_opt": 8,
        "stages": [
            {"title": "初始方案（方案⑦）", "scheme": 7, "img": "11.9.7",
             "desc": "N30 单开 3→0；N31 与 N32 合开到 A2；N20 与 N21 合开到 A1。",
             "check": "", "expect_fj": 100, "expect_cost": 1300, "opt": False},
            {"title": "调整方案（方案⑧，最优）", "scheme": 8, "img": "11.9.8",
             "desc": "压缩 N30 的到站：N30 与 N31 合开到 A1。节省 N31 在 A2 的 400，"
                     "损失 N30 在 A1 的 300，净节省 100。",
             "check": "", "expect_fj": 200, "expect_cost": 1200, "opt": True},
        ],
        "merge_text": "N31 与 N32 合开到 A2；N20 与 N21 合开到 A1。初始方案为方案⑦。",
        "final_text": "方案⑦ F节=100，方案⑧ F节=200；方案⑧较大，为最佳方案。"
                      "若把 N30 改在 A2 与 N20 合并（方案⑤），F节=100，没有改善。",
        "conclusion": "方案⑧：A3 的 N30 与 N31 合开到 A1、N32 单开；A2 的 N20 与 N21 合开到 A1；"
                      "A1 的 N10 开往 A0。",
        "obj": "F耗 = 1200 车小时；F节 = 200 车小时",
    },
    {
        "key": "xt2", "title": "习题 2", "n": 5,
        "labels": ["A4", "A3", "A2", "A1", "A0"],
        "T": [600, 600, 500, 0, 0], "t": {1: 5.0, 2: 5.0, 3: 4.0},
        "flows": [F("42", 0, 2, 170), F("41", 0, 3, 100), F("40", 0, 4, 360),
                  F("31", 1, 3, 20), F("30", 1, 4, 150), F("20", 2, 4, 200)],
        "note": "短途流 N43、N32、N21、N10 均为 0（表中以“—”表示）。",
        "abs_method": False, "combo_name": "5",
        "abs_expect": None, "abs_opt": None,
        "stages": [
            {"title": "初始方案", "combo_idx": 0, "img": "xt2_init",
             "desc": "N42、N41、N40 在 A4 分别单开；N30 单开 3→0；N20 单开 2→0；"
                     "N31 经 A2 转接。",
             "check": "", "expect_fj": 6140, "expect_cost": 3000, "opt": False},
            {"title": "调整方案（最优）", "combo_idx": 1, "img": "xt2",
             "desc": "压缩 N41 的到站：N41 并入 4→2 的列流。取消 4→1 列流节省 600，"
                     "N41 改在 A2 改编损失 500，净节省 100。",
             "check": "", "expect_fj": 6240, "expect_cost": 2900, "opt": True},
        ],
        "merge_text": "N31 与 N32 合开到 A2。初始方案：A4 的 N42、N41、N40 分别单开，"
                      "A3 的 N30 单开，A2 的 N20 单开。",
        "final_text": "初始方案 F节=6140；把 N41 并入 4→2 列流后 F节=6240，"
                      "为全枚举 150 个方案中的最大值，故调整方案最佳。",
        "conclusion": "A4 的 N40 单开 4→0，N41+N42 合并开往 A2；A3 的 N30 单开 3→0，"
                      "N31 经 A2 转接；A2 的 N20 单开 2→0，N21 与 N41、N31 开往 A1；"
                      "A1 的 N10 开往 A0。",
        "obj": "F耗 = 2900 车小时；F节 = 6240 车小时",
    },
    {
        "key": "xt3", "title": "习题 3", "n": 5,
        "labels": ["A4", "A3", "A2", "A1", "A0"],
        "T": [560, 560, 560, 0, 0], "t": {1: 3.5, 2: 2.6, 3: 3.1},
        "flows": [F("42", 0, 2, 580), F("41", 0, 3, 90), F("40", 0, 4, 200),
                  F("31", 1, 3, 20), F("30", 1, 4, 130), F("20", 2, 4, 300)],
        "note": "短途流 N43、N32、N21、N10 均为 0。",
        "abs_method": False, "combo_name": "5",
        "abs_expect": None, "abs_opt": None,
        "stages": [
            {"title": "初始方案", "combo_idx": 0, "img": "xt3_init",
             "desc": "N42 单开 4→2、N40 单开 4→0、N41 并入 4→2 列流；N30 单开 3→0；"
                     "N20 单开 2→0。",
             "check": "", "expect_fj": 3616, "expect_cost": 2526, "opt": False},
            {"title": "调整方案 1", "combo_idx": 1, "img": "xt3_s1",
             "desc": "压缩 N40 的到站：N40 改并入 4→2 列流。取消 4→0 列流节省 560，"
                     "N40 在 A2 改编损失 520，净节省 40。",
             "check": "", "expect_fj": 3656, "expect_cost": 2486, "opt": False},
            {"title": "调整方案 2（最优）", "combo_idx": 2, "img": "xt3",
             "desc": "压缩 N30 的到站/发站：N30 不再单开 3→0，改经 3→2 在 A2 与 N20 合并。"
                     "取消 3→0 列流节省 560，N30 在 A2 改编损失 338，净节省 222。",
             "check": "", "expect_fj": 3878, "expect_cost": 2264, "opt": True},
        ],
        "merge_text": "N41 与 N42 合开到 A2；N31 与 N32 合开到 A2。初始方案："
                      "N42/N41 合开 4→2，N40 单开 4→0，N30 单开 3→0，N20 单开 2→0。",
        "final_text": "F节 依次为 3616、3656、3878，调整方案 2 最大，为最佳方案。",
        "conclusion": "A4 的 N40+N41+N42 合并开往 A2；A3 全部车流经 A2 转接；"
                      "A2 的 N20 吸收 N30、N40 后单开 2→0，N21 与 N41、N31 开往 A1；"
                      "A1 的 N10 开往 A0。",
        "obj": "F耗 = 2264 车小时；F节 = 3878 车小时",
    },
]


# ============================================================ 三、方案组合
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


def stage_combo(p, st):
    if p["combo_name"] == "4":
        return combo4(*P4_ORDER[st["scheme"] - 1][:2])
    return P5[p["key"]][st["combo_idx"]]


# ============================================================ 四、符号与表格
def N(name):
    return f"N<sub>{name}</sub>"


def T_sym(n, i):
    return f"T<sub>集</sub><sup>{n - 1 - i}</sup>"


def t_sym(n, k):
    return f"t<sub>节</sub><sup>{n - 1 - k}</sup>"


def flow_label(name, q):
    return f"{N(name)}={q}"


def data_tables(p):
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


def figure(img, caption):
    return (f"<div class='figure'><img src='svg/bianzu/{img}.svg' alt='{caption}'>"
            f"<div class='figcap'>{caption}</div></div>")


def scheme_table(p, k):
    """绝对计算法：第 k 个方案的完整计算表（算例集形式）。"""
    n = p["n"]
    combo = combo4(*P4_ORDER[k - 1][:2])
    ev = evaluate(n, p["flows"], p["T"], p["t"], combo)
    adapt_by = {}
    for (name, i, j, e, q) in ev["detail"]:
        adapt_by[(name, e)] = adapt_by.get((name, e), 0) + q
    T, t = p["T"], p["t"]
    after = n - 2  # 数值列数（A2..A0 或 A3..A0）

    rows = []
    # T集 / t节
    cells = ["<td class='lbl'>T<sub>集</sub></td>"] + [f"<td>{T[i] if T[i] else ''}</td>" for i in range(n)]
    rows.append("<tr>" + "".join(cells) + "</tr>")
    cells = ["<td class='lbl'>t<sub>节</sub></td>"] + [f"<td>{t[i] if i in t else ''}</td>" for i in range(n)]
    rows.append("<tr>" + "".join(cells) + "</tr>")
    # 车流行
    for (name, i, j, q) in p["flows"]:
        cells = [f"<td colspan='2' class='lbl'>{flow_label(name, q)}</td>"]
        for kk in range(1, n):
            if kk == i:
                cells.append("<td>—</td>")
            elif i < kk < j:
                cells.append(f"<td>{adapt_by.get((name, kk), 0)}</td>")
            else:
                cells.append("<td></td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    # N改编
    sums = {kk: sum(q for (name, i, j, e, q) in ev["detail"] if e == kk) for kk in range(1, n)}
    cells = ["<td colspan='2' class='lbl'>N<sub>改编</sub></td>"]
    cells += [f"<td>{sums[kk]}</td>" for kk in range(1, n - 1)] + ["<td></td>"]
    rows.append("<tr>" + "".join(cells) + "</tr>")
    # N改编·t节
    cells = ["<td colspan='2' class='lbl'>N<sub>改编</sub>·t<sub>节</sub></td>"]
    cells += [f"<td>{sums[kk] * t[kk]:.0f}</td>" for kk in range(1, n - 1)]
    cells.append(f"<td>{ev['adapt']:.0f}</td>")
    rows.append("<tr>" + "".join(cells) + "</tr>")
    # K 行
    for i in range(n - 1):
        if not T[i]:
            continue
        cells = [f"<td colspan='2' class='lbl'>{T_sym(n, i)}={T[i]}</td>",
                 f"<td colspan='{after}'>K<sub>{n - 1 - i}</sub>={ev['k'][i]}</td>",
                 f"<td>{ev['k'][i] * T[i]:.0f}</td>"]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    # F耗
    terms = [f"{ev['adapt']:.0f}"]
    for i in range(n - 1):
        if T[i]:
            terms.append(f"{ev['k'][i] * T[i]:.0f}")
    expr = "+".join(terms) + f"={ev['cost']:.0f}"
    rows.append(f"<tr><td colspan='{n}' class='lbl'>F<sub>耗</sub></td><td><strong>{expr}</strong></td></tr>")
    head = "<tr><th></th>" + "".join(f"<th>{s}</th>" for s in p["labels"]) + "</tr>"
    return (f"<div class='table-scroll'><table class='plan-table calc-table'>"
            f"<thead>{head}</thead><tbody>{''.join(rows)}</tbody></table></div>")


def calc_table(p, combo, mode="marks"):
    """表格计算法：完整计算表（mode=values 时只填 N·t 值）。"""
    n = p["n"]
    flows, T, t = p["flows"], p["T"], p["t"]
    ev = evaluate(n, flows, T, t, combo)
    abs_set = absolute_flows(n, flows, T, t)

    rows = []
    cells = ["<td class='lbl'>T<sub>集</sub></td>"] + [f"<td>{T[i] if T[i] else ''}</td>" for i in range(n)]
    rows.append("<tr>" + "".join(cells) + "</tr>")
    cells = ["<td class='lbl'>t<sub>节</sub></td>"] + [f"<td>{t[i] if i in t else ''}</td>" for i in range(n)]
    rows.append("<tr>" + "".join(cells) + "</tr>")
    # 车流行
    for (name, i, j, q) in flows:
        cells = [f"<td colspan='2' class='lbl'>{flow_label(name, q)}</td>"]
        for kk in range(1, n):
            if kk == i:
                cells.append("<td>—</td>")
            elif i < kk < j:
                val = q * t[kk]
                if mode == "values":
                    cells.append(f"<td>{val:.0f}</td>")
                elif (name, kk) in ev["through"]:
                    mark = "△" if (name in abs_set and kk == j - 1) else "○"
                    cls = "mark-t" if mark == "△" else "mark-o"
                    cells.append(f"<td>{val:.0f}<span class='{cls}'>{mark}</span></td>")
                else:
                    cells.append(f"<td class='muted'>{val:.0f}</td>")
            else:
                cells.append("<td></td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    if mode == "values":
        head = "<tr><th></th>" + "".join(f"<th>{s}</th>" for s in p["labels"]) + "</tr>"
        return (f"<div class='table-scroll'><table class='plan-table calc-table'>"
                f"<thead>{head}</thead><tbody>{''.join(rows)}</tbody></table></div>")
    # N改编
    sums = {kk: sum(q for (name, i, j, e, q) in ev["detail"] if e == kk) for kk in range(1, n)}
    cells = ["<td colspan='2' class='lbl'>N<sub>改编</sub></td>"]
    cells += [f"<td>{sums[kk] if sums[kk] else ''}</td>" for kk in range(1, n - 1)] + ["<td></td>"]
    rows.append("<tr>" + "".join(cells) + "</tr>")
    cells = ["<td colspan='2' class='lbl'>N<sub>改编</sub>·t<sub>节</sub></td>"]
    cells += [f"<td>{sums[kk] * t[kk]:.0f}</td>" for kk in range(1, n - 1)]
    cells.append(f"<td>{ev['adapt']:.0f}</td>")
    rows.append("<tr>" + "".join(cells) + "</tr>")
    # K 行
    after = n - 2
    for i in range(n - 1):
        if not T[i]:
            continue
        cells = [f"<td colspan='2' class='lbl'>{T_sym(n, i)}={T[i]}</td>",
                 f"<td colspan='{after}'>K<sub>{n - 1 - i}</sub>={ev['k'][i]}</td>",
                 f"<td>{ev['k'][i] * T[i]:.0f}</td>"]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    ts = through_sum(flows, t, ev["through"])
    train = sum(ev["k"][i] * T[i] for i in range(n))
    fj = ts - train
    rows.append(f"<tr><td colspan='{n}' class='lbl'>F<sub>节</sub></td>"
                f"<td><strong>{ts:.0f}−{train:.0f}={fj:.0f}</strong></td></tr>")
    head = "<tr><th></th>" + "".join(f"<th>{s}</th>" for s in p["labels"]) + "</tr>"
    return (f"<div class='table-scroll'><table class='plan-table calc-table'>"
            f"<thead>{head}</thead><tbody>{''.join(rows)}</tbody></table></div>")


# ============================================================ 五、步骤文本
def condition_texts(p):
    n = p["n"]
    abs_lines, nec_lines = [], []
    for (name, i, j, q) in p["flows"]:
        ks = list(range(i + 1, j))
        vals = [q * p["t"][k] for k in ks]
        mn = min(vals)
        km = ks[vals.index(mn)]
        expr = f"{N(name)}·{t_sym(n, km)} = {q}×{p['t'][km]} = {mn:.0f}"
        if mn >= p["T"][i]:
            abs_lines.append(f"<p>{expr} ≥ {T_sym(n, i)} = {p['T'][i]}，"
                             f"满足绝对条件，必须单开直达（△）。</p>")
        else:
            abs_lines.append(f"<p>{expr} ＜ {T_sym(n, i)} = {p['T'][i]}，不满足绝对条件。</p>")
            s = sum(vals)
            ts = "+".join(t_sym(n, k) for k in ks)
            expr2 = (f"{N(name)}·({ts}) = {q}×({' + '.join(str(p['t'][k]) for k in ks)}) "
                     f"= {s:.0f}")
            if s >= p["T"][i]:
                nec_lines.append(f"<p>{expr2} ≥ {T_sym(n, i)} = {p['T'][i]}，"
                                 f"满足必要条件，暂定单开（○）。</p>")
            else:
                nec_lines.append(f"<p>{expr2} ＜ {T_sym(n, i)} = {p['T'][i]}，"
                                 f"不满足必要条件，与相邻车流合并。</p>")
    return abs_lines, nec_lines


def stage_stats(p, st):
    combo = stage_combo(p, st)
    ev = evaluate(p["n"], p["flows"], p["T"], p["t"], combo)
    ts = through_sum(p["flows"], p["t"], ev["through"])
    train = sum(ev["k"][i] * p["T"][i] for i in range(p["n"]))
    fj = ts - train
    assert abs(ev["cost"] - st["expect_cost"]) < 1e-6, (p["key"], st["title"], ev["cost"])
    assert abs(fj - st["expect_fj"]) < 1e-6, (p["key"], st["title"], fj)
    if p["combo_name"] == "4":
        c = p["abs_expect"][9]
        verify = (f"经绝对计算法验证：F耗(方案⑩) − F耗(方案{'①②③④⑤⑥⑦⑧⑨⑩'[st['scheme']-1]}) "
                  f"= {c} − {ev['cost']:.0f} = {fj:.0f} = F节。")
    else:
        c = sum(q * sum(p["t"][k] for k in range(i + 1, j))
                for (name, i, j, q) in p["flows"])
        verify = f"用全改编基线验证：C − F耗 = {c:.0f} − {ev['cost']:.0f} = {fj:.0f} = F节。"
    return combo, ev, ts, train, fj, verify


def abs_method(p):
    out = ["<h3>绝对计算法</h3>",
           "<h4>第一步，枚举所有方案，画出列车到达站图。</h4>",
           f"<p>{p['n']} 个支点站方向共 {len(P4_ORDER)} 个编组方案，逐方案计算如下。</p>",
           "<h4>第二步，列出绝对计算法表格：明确非短途直达车流的量，"
           "根据到站图填写直达车流无改编通过的量为 0，剩余为车流量，"
           "并计算改编车小时、集结车小时与目标函数值。</h4>"]
    costs = []
    for k in range(1, len(P4_ORDER) + 1):
        combo = combo4(*P4_ORDER[k - 1][:2])
        ev = evaluate(p["n"], p["flows"], p["T"], p["t"], combo)
        costs.append(ev["cost"])
        out.append(f"<div class='scheme-block'><h5>方案{'①②③④⑤⑥⑦⑧⑨⑩'[k-1]}"
                   f"（{P4_ORDER[k-1][2]}）</h5>")
        out.append(figure(f"11.9.{k}", f"方案{'①②③④⑤⑥⑦⑧⑨⑩'[k-1]}的列车到达站图"))
        out.append(scheme_table(p, k))
        out.append("</div>")
    best = min(range(len(costs)), key=lambda i: costs[i]) + 1
    assert best == p["abs_opt"], (p["key"], best, p["abs_opt"])
    out.append("<h4>第三步，找到车小时消耗最小的方案。</h4>")
    out.append(f"<p>方案{'①②③④⑤⑥⑦⑧⑨⑩'[best-1]} 的 F耗 最小，"
               f"为 {costs[best-1]:.0f} 车小时，为最佳方案。</p>")
    return out


def table_method(p):
    out = ["<h3>表格计算法</h3>",
           "<h4>第 1 步，根据车流量计算所有的 N<sub>通</sub>·t<sub>节</sub> 值，"
           "并填入计算表。</h4>",
           calc_table(p, stage_combo(p, p["stages"][0]), "values")]
    abs_lines, nec_lines = condition_texts(p)
    out += ["<h4>第 2 步，计算绝对条件、必要条件，确定初始方案，并计算目标函数值。</h4>",
            "<h5>（1）绝对条件的判断</h5>", *abs_lines,
            "<h5>（2）必要条件的判断</h5>", *nec_lines,
            "<h5>（3）其余车流的合并</h5>", f"<p>{p['merge_text']}</p>"]

    # 初始方案
    st = p["stages"][0]
    combo, ev, ts, train, fj, verify = stage_stats(p, st)
    expr = P4_ORDER[st["scheme"] - 1][2] if p["combo_name"] == "4" else ""
    title = st["title"] + (f"（{expr}）" if expr else "")
    out += [f"<h5>{title}</h5>", f"<p>{st['desc']}</p>", calc_table(p, combo),
            figure(st["img"], f"{p['title']} · {st['title']}"),
            f"<p class='calc-line'>F<sub>节</sub> = {ts:.0f} − {train:.0f} = {fj:.0f} 车小时。</p>",
            f"<p>{verify}</p>"]
    if st.get("check"):
        out.append(f"<p>{st['check']}</p>")

    out.append("<h4>第 3 步，调整初始方案，使用绝对条件验证方案可行性，"
               "做出计算表格和列车到达站图，然后比较所有调整方案目标函数值。</h4>")
    for st in p["stages"][1:]:
        combo, ev, ts, train, fj, verify = stage_stats(p, st)
        expr = P4_ORDER[st["scheme"] - 1][2] if p["combo_name"] == "4" else ""
        title = st["title"] + (f"（{expr}）" if expr else "")
        out += [f"<h5>{title}</h5>", f"<p>{st['desc']}</p>"]
        if st.get("check"):
            out.append(f"<p>{st['check']}</p>")
        out += [calc_table(p, combo),
                figure(st["img"], f"{p['title']} · {st['title']}"),
                f"<p class='calc-line'>F<sub>节</sub> = {ts:.0f} − {train:.0f} = {fj:.0f} 车小时。</p>",
                f"<p>{verify}</p>"]
    out += ["<h4>第 4 步，比较目标函数值，确定最佳方案。</h4>",
            f"<p>{p['final_text']}</p>"]
    return out


def problem_panel(p):
    out = [f"<section class='card problem-panel' id='p-{p['key']}' hidden>",
           f"<h2>{p['title']} · {p['n']} 个支点站（{p['labels'][0]}–{p['labels'][-1]}）</h2>",
           "<h3>已知信息</h3>", data_tables(p), f"<p class='note'>{p['note']}</p>"]
    if p["abs_method"]:
        out += abs_method(p)
    out += table_method(p)
    out += ["<h3>结论</h3>",
            f"<div class='result-box'><p><strong>最优方案：</strong>{p['conclusion']}</p>"
            f"<p><strong>目标函数值：</strong>{p['obj']}（F节 为相对全改编基线的节省）</p></div>",
            "</section>"]
    return "\n".join(out)


# ============================================================ 六、页面骨架
CSS = """
.toc{display:none}
.plan-table{border-collapse:collapse;width:100%;margin:8px 0 4px;font-size:13px}
.plan-table th,.plan-table td{border:1px solid #dcdfe6;padding:5px 7px;text-align:center;vertical-align:middle}
.plan-table th{background:#f5f7fa;font-weight:600;white-space:nowrap}
.plan-table td.lbl{text-align:left;white-space:nowrap}
.plan-table td.muted{color:#999}
.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.calc-table{table-layout:fixed}
.calc-table td{padding:4px 6px}
#selectedInfo{margin-top:10px}
.figure{text-align:center;margin:12px 0 6px}
.figure img{max-width:100%;height:auto;background:#fff;border:1px solid #eee;border-radius:4px;padding:6px}
.figcap{color:#666;font-size:13px;margin-top:4px;text-align:center}
.result-box{border-left:4px solid #1890ff;background:#f0f7ff;padding:10px 14px;border-radius:4px;margin-top:12px;font-size:14px}
.result-box strong{color:#0b4f9e}
.note{color:#666;font-size:13px;margin:6px 0}
.legend{font-size:13px;color:#555;margin:4px 0 0}
.mark-o{color:#1d7a46;margin-left:1px}
.mark-t{color:#b26a00;margin-left:1px;font-weight:700}
.problem-panel[hidden]{display:none!important}
.problem-panel h2{font-size:18px;color:#1a1a2e;margin-bottom:10px;padding-bottom:8px;border-bottom:2px solid #e8e8e8}
.problem-panel h3{font-size:16px;color:#1a1a2e;margin:18px 0 8px;padding-bottom:5px;border-bottom:1px solid #eee}
.problem-panel h4{font-size:14px;color:#1a1a2e;margin:14px 0 6px}
.problem-panel h5{font-size:14px;color:#333;margin:10px 0 4px}
.calc-line{font-size:14px;color:#1a1a2e;margin:6px 0}
.scheme-block{border:1px solid #eee;border-radius:6px;padding:10px 12px;margin:14px 0;background:#fcfcfd}
.scheme-block h5{margin:0 0 6px;font-size:14px;color:#1a1a2e}
.preset.active{background:#1890ff;color:#fff;border-color:#1890ff}
@media (max-width:600px){.problem-panel h3{font-size:15px}.calc-table{font-size:12px}}
"""

JS = """
(function () {
  var btns = Array.prototype.slice.call(document.querySelectorAll('.problem-btn'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('.problem-panel'));
  var infoEl = document.getElementById('selectedInfo');
  function show(id, scroll, info) {
    panels.forEach(function (p) { p.hidden = (p.id !== id); });
    btns.forEach(function (b) { b.classList.toggle('active', b.dataset.target === id); });
    if (infoEl && info) infoEl.textContent = info;
    if (scroll) {
      var el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
  btns.forEach(function (b) {
    b.addEventListener('click', function () { show(b.dataset.target, true, b.dataset.info); });
  });
  var h = location.hash.replace('#', '');
  if (h) {
    var selected = btns.filter(function (b) { return b.dataset.target === h; })[0];
    if (selected) show(h, false, selected.dataset.info);
  }
})();
"""


def selector_card():
    def button(p):
        n = p["n"]
        T_str = "，".join(f"{p['labels'][i]}={p['T'][i]}" for i in range(n) if p["T"][i])
        t_str = "，".join(f"{p['labels'][i]}={p['t'][i]}" for i in range(n) if i in p["t"])
        flow_str = "，".join(f"N{name}={q}" for (name, i, j, q) in p["flows"])
        info = (f"{n} 个支点站（{p['labels'][0]}–{p['labels'][-1]}） · "
                f"T集：{T_str} · t节：{t_str} · 非短途车流：{flow_str}")
        label = p["title"].replace(" ", "")
        return (f"<button type='button' class='btn-sm preset problem-btn' "
                f"data-target='p-{p['key']}' data-info=\"{info}\">{label}</button>")

    ex = [p for p in PROBLEMS if p["key"].startswith("ex")]
    xt = [p for p in PROBLEMS if p["key"].startswith("xt")]
    return (f"<section class='card' id='selector'><h2>选择算例</h2>"
            f"<div class='preset-row'>"
            f"<span class='preset-label'>例题：</span>"
            + "".join(button(p) for p in ex) +
            f"<span class='preset-label' style='margin-left:12px'>习题：</span>"
            + "".join(button(p) for p in xt) +
            f"</div>"
            f"<p class='note' id='selectedInfo'>点击上方题目按钮，查看该题的已知信息、"
            f"完整计算过程与最优方案。</p></section>")


def build():
    # ---------- 断言 ----------
    for p in PROBLEMS:
        n = p["n"]
        if p["combo_name"] == "4":
            got = [evaluate(n, p["flows"], p["T"], p["t"],
                            combo4(*P4_ORDER[k][:2]))["cost"]
                   for k in range(len(P4_ORDER))]
            assert got == p["abs_expect"], (p["key"], got)
            assert got[p["abs_opt"] - 1] == min(got)
        else:
            dests = [[j for j in range(i + 1, n)] for i in range(n)]
            allp = [list(partitions(d)) if d else [[]] for d in dests]
            best = min(evaluate(n, p["flows"], p["T"], p["t"], c)["cost"]
                       for c in product(*allp))
            opt = next(s for s in p["stages"] if s["opt"])
            assert abs(best - evaluate(n, p["flows"], p["T"], p["t"],
                                       stage_combo(p, opt))["cost"]) < 1e-6
        for st in p["stages"]:
            stage_stats(p, st)
    # 绝对条件（min/≥）回归
    xt3 = next(p for p in PROBLEMS if p["key"] == "xt3")
    af3 = absolute_flows(xt3["n"], xt3["flows"], xt3["T"], xt3["t"])
    assert "42" in af3 and "20" in af3 and "40" not in af3, af3
    xt2 = next(p for p in PROBLEMS if p["key"] == "xt2")
    af2 = absolute_flows(xt2["n"], xt2["flows"], xt2["T"], xt2["t"])
    assert "30" in af2, af2

    # ---------- 生成图 ----------
    os.makedirs(SVG_OUT, exist_ok=True)
    needed = {st["img"] for p in PROBLEMS for st in p["stages"]}
    needed |= {f"11.9.{k}" for k in range(1, 11)}
    schemes = {s["name"]: s for s in draw_scheme.SCHEMES}
    for name in sorted(needed):
        assert name in schemes, f"draw_scheme.SCHEMES 缺少 {name}"
        with open(os.path.join(SVG_OUT, f"{name}.svg"), "w", encoding="utf-8") as f:
            f.write(draw_scheme.build(schemes[name]))

    # ---------- 生成页面 ----------
    body = "\n".join(problem_panel(p) for p in PROBLEMS)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>列车编组计划 · 铁路行车组织算例教学演示</title>
<link rel="stylesheet" href="style.css">
<style>{CSS}</style>
</head>
<body>
<div class="container">
<header class="site-header">
  <h1>铁路行车组织算例教学演示</h1>
  <nav class="top-tabs" aria-label="主导航">
    <a href="/">调车作业计划</a>
    <a href="/bianzu" class="active">列车编组计划</a>
    <a href="/qa">教材问答</a>
  </nav>
  <p class="subtitle">列车编组计划 · 绝对计算法 / 表格计算法 · 3 道例题 + 3 道习题</p>
</header>
<main>
{selector_card()}
<div id="resultRoot">
{body}
</div>
</main>
<footer>
  <p>© 2026 钱晨 上海应用技术大学 · 保留所有权利</p>
</footer>
</div>
<script>{JS}</script>
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
