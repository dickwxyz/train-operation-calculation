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
import copy
import json
from collections import deque
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
             "desc": "N30 单开 3→0。",
             "check": "", "expect_fj": 200, "expect_cost": 1220, "opt": False},
            {"title": "调整方案 1（方案⑧，最优）", "scheme": 8, "img": "11.9.8",
             "desc": "压缩 N30 的到站：N30 与 N31 合开到 A1。节省 N31 在 A2 的通过 480，"
                     "损失 N30 在 A1 的改编 300，净节省 180。",
             "check": "经验证，N30 在 A1 的通过节省 300＜T集³=500，不满足绝对条件，可以与 N31 合并。",
             "expect_fj": 380, "expect_cost": 1040, "opt": True},
            {"title": "调整方案 2（方案⑤）", "scheme": 5, "img": "11.9.5",
             "desc": "压缩 N30 的发站：N30 改经 A2 与 N20 合并。取消 3→0 列流节省 500，"
                     "N30 在 A2 由无改编通过变为改编损失 400；新开 2→0 列流增加 600，"
                     "N20 在 A1 由改编变为无改编通过节省 240，净 −260。",
             "check": "经验证，N30 在 A2 的通过节省 400＜T集²=600，不满足绝对条件，可以与 N20 合并。",
             "expect_fj": -60, "expect_cost": 1480, "opt": False},
        ],
        "merge_text": "（1）（2）均不满足的剩余车流为 N31（A3→A1）和 N20（A2→A0）。两者始发站不同，"
                      "不能合开同一支直达列流；交集区段只有 A2–A1（发站编号−到站编号＝1＜2），"
                      "合并后只能编入相邻车站间开行的摘挂列车，形成不了非短途直达列流，因此无法合并。"
                      "N31、N20 随相邻车站开行的列车改编走行，初始方案只有 N30 单开 3→0（方案⑦）。",
        "final_text": "三个方案的 F节 分别为 200、380、−60，调整方案 1（方案⑧）最大，故为最佳方案。",
        "conclusion": "方案⑧：A3 的 N30 与 N31 合开到 A1。",
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
             "desc": "N30 单开 3→0；N20 单开 2→0。",
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
        "merge_text": "（1）（2）均不满足的剩余车流只有 N31（A3→A1）。N31 与 N20 的交集只有 A2–A1"
                      "（发站编号−到站编号＝1＜2），只能编入摘挂列车；与 N30 的交集为 A3–A1，"
                      "但 N30 已满足必要条件①暂定单开，把 N31 并入其到达站相当于压缩 N30 的到站，"
                      "留待第 3 步判断。初始方案中 N31 随相邻车站开行的列车改编走行，"
                      "N30 单开 3→0、N20 单开 2→0（方案②）。",
        "final_text": "过渡方案Ⅱ 的 F节=360 大于过渡方案Ⅰ 的 355 和初始方案的 320，"
                      "故方案⑤为最佳方案。",
        "conclusion": "方案⑤：A2 的 N30 与 N20 合开到 A0。",
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
                     "N20 与 N40 在 A2 合开 2→0。",
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
        "merge_text": "（1）（2）均不满足的剩余车流为 N42、N40、N31。A4 的 N42、N40 同发站合开："
                      "ΣN＝180+60＝240，合并后无改编通过 A3 的节省 240×2.5＝600 ≥ T集⁴＝600，"
                      "满足必要条件②，合开 4→2 直达。A3 的 N31（A3→A1）没有同发站的剩余车流可合开；"
                      "与 4→2 列流的交集只有 A3–A2（发站编号−到站编号＝1＜2），只能编入摘挂列车，"
                      "故不合并，随相邻车站开行的列车改编走行。初始方案：N41 单开 4→1，"
                      "N42 与 N40 合开 4→2，N30 单开 3→0，N20 与 N40 在 A2 合开 2→0（图 11.20）。",
        "final_text": "四个阶段的 F节 依次为 1095、1305、1345、1465，最佳方案 F节=1465。",
        "conclusion": "A4 的 N40 与 N41 合开到 A1；A2 的 N20 与 N30 合开到 A0。",
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
             "desc": "N30 单开 3→0。",
             "check": "", "expect_fj": 100, "expect_cost": 1300, "opt": False},
            {"title": "调整方案 1（方案⑧，最优）", "scheme": 8, "img": "11.9.8",
             "desc": "压缩 N30 的到站：N30 与 N31 合开到 A1。节省 N31 在 A2 的 400，"
                     "损失 N30 在 A1 的 300，净节省 100。",
             "check": "", "expect_fj": 200, "expect_cost": 1200, "opt": True},
            {"title": "调整方案 2（方案⑤）", "scheme": 5, "img": "11.9.5",
             "desc": "压缩 N30 的发站：N30 改经 A2 与 N20 合并开行 2→0。取消 3→0 列流节省 600，"
                     "N30 在 A2 由无改编通过变为改编损失 400；新开 2→0 列流增加 500，"
                     "N20 在 A1 由改编变为无改编通过节省 300，净 0，F节 仍为 100。",
             "check": "经验证，N30 在 A2 的通过节省 400＜T集²=500，不满足绝对条件，可以与 N20 合并。",
             "expect_fj": 100, "expect_cost": 1300, "opt": False},
        ],
        "merge_text": "（1）（2）均不满足的剩余车流为 N31（A3→A1）和 N20（A2→A0）。两者始发站不同，"
                      "不能合开同一支直达列流；交集区段只有 A2–A1（发站编号−到站编号＝1＜2），"
                      "合并后只能编入摘挂列车，形成不了非短途直达列流，因此无法合并。"
                      "初始方案只有 N30 单开 3→0（方案⑦）。",
        "final_text": "方案⑦ F节=100，方案⑧ F节=200；方案⑧较大，为最佳方案。"
                      "若把 N30 改在 A2 与 N20 合并（方案⑤），F节=100，没有改善。",
        "conclusion": "方案⑧：A3 的 N30 与 N31 合开到 A1。",
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
             "desc": "N42、N41、N40 在 A4 分别单开；N30 单开 3→0；N20 单开 2→0。",
             "check": "", "expect_fj": 6140, "expect_cost": 3000, "opt": False},
            {"title": "调整方案（最优）", "combo_idx": 1, "img": "xt2",
             "desc": "压缩 N41 的到站：N41 并入 4→2 的列流。取消 4→1 列流节省 600，"
                     "N41 改在 A2 改编损失 500，净节省 100。",
             "check": "", "expect_fj": 6240, "expect_cost": 2900, "opt": True},
        ],
        "merge_text": "（1）（2）均不满足的剩余车流只有 N31（A3→A1）。N31 与 N42 的交集只有 A3–A2"
                      "（发站编号−到站编号＝1＜2），只能编入摘挂列车；与 N30 的交集为 A3–A1，"
                      "但 N30 满足绝对条件（150×4＝600 ≥ T集³＝600），不能在 A1 改编，"
                      "不能把 N31 并入其到达站。初始方案中 N31 随相邻车站开行的列车经 A2 转接；"
                      "A4 的 N42、N41、N40 分别单开，A3 的 N30 单开 3→0，A2 的 N20 单开 2→0。",
        "final_text": "初始方案 F节=6140；把 N41 并入 4→2 列流后 F节=6240，"
                      "为全枚举 150 个方案中的最大值，故调整方案最佳。",
        "conclusion": "A4 的 N41 与 N42 合开到 A2，N40 单开到 A0；A3 的 N30 单开到 A0；"
                      "A2 的 N20 单开到 A0。",
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
        "merge_text": "（1）（2）均不满足的剩余车流为 N41、N31。N41 单独开 4→1 时 "
                      "90×(3.5+2.6)＝549 ＜ T集⁴＝560，不满足必要条件②；N41 与 N42 合开到 A2 时 "
                      "ΣN＝580+90＝670、通过 A3 的节省 670×3.5＝2345 ≥ T集⁴＝560，"
                      "满足必要条件②，故 N41 与 N42 合开到 A2。A3 的 N31（A3→A1）没有同发站的"
                      "剩余车流可合开，与 4→2 列流的交集只有 A3–A2（发站编号−到站编号＝1＜2），"
                      "只能编入摘挂列车，故不合并。初始方案：N41 与 N42 合开 4→2，N40 单开 4→0，"
                      "N30 单开 3→0，N20 单开 2→0。",
        "final_text": "F节 依次为 3616、3656、3878，调整方案 2 最大，为最佳方案。",
        "conclusion": "A4 的 N40、N41、N42 合开到 A2；A2 的 N20 与 N30 合开到 A0。",
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
    if "combo" in st:
        return st["combo"]
    if p["combo_name"] == "4":
        return combo4(*P4_ORDER[st["scheme"] - 1][:2])
    return P5[p["key"]][st["combo_idx"]]


# ============================================================ 三、通用求解器（编辑数据后重算）
def canon_combo(combo):
    return tuple(tuple(sorted(tuple(sorted(b)) for b in blocks)) for blocks in combo)


def combo_metrics(p, combo):
    ev = evaluate(p["n"], p["flows"], p["T"], p["t"], combo)
    ts = through_sum(p["flows"], p["t"], ev["through"])
    train = sum(ev["k"][i] * p["T"][i] for i in range(p["n"]))
    return ev, ts, train, ts - train


def all_combos(p):
    n = p["n"]
    dests = [[j for j in range(i + 1, n)] for i in range(n)]
    allp = [list(partitions(d)) if d else [[]] for d in dests]
    out = []
    for c in product(*allp):
        out.append(tuple(tuple(sorted(b)) for b in c))
    return out


def initial_combo(p):
    """按绝对/必要条件构造初始方案（最大可能的直达方案）。"""
    n, T, t = p["n"], p["T"], p["t"]
    by_origin = {}
    for (name, i, j, q) in p["flows"]:
        by_origin.setdefault(i, []).append((name, j, q))
    combo = []
    for i in range(n):
        here = by_origin.get(i, [])
        if i == n - 1:
            combo.append(())
            continue
        adj = i + 1
        fixed, rest = [], []
        for (name, j, q) in here:
            ks = list(range(i + 1, j))
            vals = [q * t[k] for k in ks]
            if vals and (min(vals) >= T[i] or sum(vals) >= T[i]):
                fixed.append(j)
            else:
                rest.append((name, j, q))
        blocks = [[j] for j in sorted(fixed)]
        rest_q = {j: q for (_, j, q) in rest}
        best = None
        for part in partitions(list(rest_q.keys())):
            valid, invalid = [], []
            for b in part:
                e = min(b)
                sumN = sum(rest_q[j] for j in b)
                sumt = sum(t[k] for k in range(i + 1, e))
                if sumN * sumt >= T[i] and sumt > 0:
                    valid.append(list(b))
                else:
                    invalid.append(list(b))
            score = (len(valid), -len(part), sum(min(b) for b in valid))
            if best is None or score > best[0]:
                best = (score, valid, invalid)
        _, valid, invalid = best
        blocks += [list(b) for b in valid]
        loose = sorted([j for b in invalid for j in b], reverse=True)
        adj_block = [adj]
        for j in loose:
            cands = [(min(b), idx) for idx, b in enumerate(blocks) if min(b) <= j]
            if cands:
                _, idx = max(cands)
                blocks[idx].append(j)
            else:
                adj_block.append(j)
        blocks.append(adj_block)
        combo.append(tuple(tuple(sorted(b)) for b in blocks))
    return tuple(combo)


def optimal_combo(p):
    best = None
    for c in all_combos(p):
        ev, ts, train, fj = combo_metrics(p, c)
        key = (ev["cost"], -fj, canon_combo(c))
        if best is None or key < best[0]:
            best = (key, c, ev, ts, train, fj)
    return best[1:]


def neighbor_moves(p, combo):
    """单支车流换块的邻居（只返回 F节 严格增加的边）。"""
    n = p["n"]
    base_ev, _, _, base_fj = combo_metrics(p, combo)
    seen = set()
    out = []
    for i in range(n):
        for bi, block in enumerate(combo[i]):
            for d in block:
                if d == i + 1:      # 相邻短途流不参与压缩
                    continue
                old_min = min(block)
                base = [list(b) for idx, b in enumerate(combo[i]) if idx != bi]
                old = [x for x in block if x != d]
                variants = [base + ([old] if old else []) + [[d]]]
                for bj, b in enumerate(base):
                    if min(b) <= d:
                        nb = b + [d]
                        variants.append(base[:bj] + [nb] + base[bj + 1:] + ([old] if old else []))
                if not any(i + 1 in b for b in base):
                    variants.append(base + ([old] if old else []) + [[i + 1, d]])
                for nb_blocks in variants:
                    new_combo = list(combo)
                    new_combo[i] = tuple(tuple(sorted(b)) for b in nb_blocks if b)
                    new_combo = tuple(new_combo)
                    ck = canon_combo(new_combo)
                    if ck in seen:
                        continue
                    seen.add(ck)
                    ev, ts, train, fj = combo_metrics(p, new_combo)
                    if fj <= base_fj + 1e-9:
                        continue
                    new_block = next(b for b in new_combo[i] if d in b)
                    out.append((new_combo, (i, d, old_min, min(new_block)), fj - base_fj))
    return out


def improvement_path(p, start, target):
    """BFS 一条 F节 严格增加的路径；失败时退回贪心 + 追加全枚举最优。"""
    sk, tk = canon_combo(start), canon_combo(target)
    if sk == tk:
        return [(start, None, 0.0)]
    info = {sk: (start, None, None, 0.0)}
    q = deque([sk])
    while q:
        ck = q.popleft()
        cur = info[ck][0]
        for nb, meta, delta in neighbor_moves(p, cur):
            nk = canon_combo(nb)
            if nk in info:
                continue
            info[nk] = (nb, ck, meta, delta)
            if nk == tk:
                path = []
                k = nk
                while k is not None:
                    combo, parent, mv, dl = info[k]
                    path.append((combo, mv, dl))
                    k = parent
                path.reverse()
                return path
            q.append(nk)
    # 贪心兜底
    path = [(start, None, 0.0)]
    cur = start
    while True:
        moves = neighbor_moves(p, cur)
        if not moves:
            break
        nb, meta, delta = max(moves, key=lambda x: x[2])
        path.append((nb, meta, delta))
        cur = nb
    if canon_combo(cur) != tk:
        path.append((target, None, 0.0))
    return path


def expr_from_combo(combo, n):
    out = []
    for blocks in combo:
        if not blocks:
            continue
        groups = []
        for b in blocks:
            nums = sorted(n - 1 - x for x in b)
            groups.append("+".join(str(x) for x in nums))
        groups.sort(key=lambda s: (int(s.split("+")[0]), len(s)))
        out.append(",".join(groups))
    return "; ".join(out)


def diagram_scheme(p, combo):
    """由编组方案生成到达站图（直达在上、主链在下）。"""
    n = p["n"]
    name_by = {(i, j): name for (name, i, j, q) in p["flows"]}
    endpoints = [set(min(b) for b in blocks) for blocks in combo]
    legs = {}
    for (name, i, j, q) in p["flows"]:
        m = i
        block = next(b for b in combo[m] if j in b)
        e = min(block)
        while True:
            legs.setdefault((m, e), []).append((i, name))
            if e >= j:
                break
            m = e
            e = max([x for x in endpoints[m] if x <= j] + [m + 1])
    for i in range(n - 1):
        adj_name = f"{n - 1 - i}{n - 2 - i}"
        legs.setdefault((i, i + 1), []).append((i, adj_name))
    items = []
    for (m, e), labels in legs.items():
        names = [nm for (_, nm) in sorted(set(labels), key=lambda x: (x[0], x[1]))]
        items.append({"from": m, "to": e, "terms": tuple(names)})
    units = sorted([x for x in items if x["to"] == x["from"] + 1], key=lambda x: x["from"])
    directs = sorted([x for x in items if x["to"] > x["from"] + 1],
                     key=lambda x: (x["from"], -x["to"]))
    chain_row = len(directs)
    lines = []
    for r, x in enumerate(directs):
        lines.append({"row": r, "from": x["from"], "to": x["to"], "terms": x["terms"]})
    for x in units:
        lines.append({"row": chain_row, "from": x["from"], "to": x["to"], "terms": x["terms"]})
    return {"name": "runtime", "row_gap": 80, "x0": 80, "stations": "auto", "lines": lines}


def move_desc(p, meta, delta):
    i, d, old_min, new_min = meta
    name = next(nm for (nm, oi, oj, q) in p["flows"] if oi == i and oj == d)
    n = p["n"]
    a_old = f"A{n - 1 - old_min}"
    a_new = f"A{n - 1 - new_min}"
    if old_min == new_min:
        return (f"{N(name)} 改换编组去向（终点仍为 {a_new}），"
                f"F节 增加 {delta:.0f} 车小时。")
    return (f"压缩 {N(name)} 的到站/发站：由终点 {a_old} 改为 {a_new}，"
            f"F节 增加 {delta:.0f} 车小时。")


def remaining_flows(p):
    """（1）绝对条件、（2）必要条件① 都不满足的剩余直达车流。"""
    out = []
    for (name, i, j, q) in p["flows"]:
        vals = [q * p["t"][k] for k in range(i + 1, j)]
        if not vals:
            continue
        if min(vals) >= p["T"][i] or sum(vals) >= p["T"][i]:
            continue
        out.append((name, i, j, q))
    return out


def merge_reasoning(p):
    """第 2 步（3）的说明：剩余车流按必要条件②（式 11.14）能否合开。"""
    n, T, t = p["n"], p["T"], p["t"]
    rem = remaining_flows(p)
    if not rem:
        return "（1）（2）已确定全部车流的编组方式，没有剩余车流需要合并。"
    names = "、".join(N(name) for (name, i, j, q) in rem)
    parts = [f"（1）（2）均不满足的剩余车流为 {names}。" if len(rem) > 1
             else f"（1）（2）均不满足的剩余车流只有 {names}。"]
    combo = initial_combo(p)
    seen = set()
    for (name, i, j, q) in rem:
        blk = next(b for b in combo[i] if j in b)
        e = min(blk)
        key = (i, tuple(blk))
        if e <= i + 1 or key in seen:
            continue
        seen.add(key)
        group = [(nm, qq) for (nm, oi, oj, qq) in p["flows"] if oi == i and oj in blk]
        sumN = sum(qq for (nm, qq) in group)
        sumt = sum(t[k] for k in range(i + 1, e))
        saving = sumN * sumt
        a_i, a_e = f"A{n - 1 - i}", f"A{n - 1 - e}"
        gnames = "、".join(N(nm) for (nm, qq) in group)
        cmp = "≥" if saving >= T[i] else "＜"
        verdict = "满足" if saving >= T[i] else "不满足"
        parts.append(f"{a_i} 的 {gnames} 合并开往 {a_e}：ΣN＝{fmt(sumN)}，无改编通过沿途支点站的"
                     f"节省 {fmt(sumN)}×{fmt(sumt)}＝{fmt(saving)} {cmp} T集＝{fmt(T[i])}，"
                     f"{verdict}必要条件②。")
    adj = []
    for (name, i, j, q) in rem:
        if min(next(b for b in combo[i] if j in b)) <= i + 1:
            adj.append(N(name))
    if adj:
        parts.append(f"{'、'.join(adj)} 只能随相邻车站开行的列车改编走行，"
                     f"形成不了非短途直达列流。")
    parts.append(f"初始方案为 {expr_from_combo(combo, n)}。")
    return "".join(parts)


def conclusion_from_combo(p, combo):
    """最优方案描述：只写开行的非短途直达列流（发站编号−到站编号≥2）。"""
    n = p["n"]
    parts = []
    for i, blocks in enumerate(combo):
        for blk in blocks:
            e = min(blk)
            if e - i < 2:
                continue
            names = [nm for (nm, oi, oj, q) in p["flows"] if oi == i and oj in blk]
            if not names:
                continue
            verb = "合开到" if len(names) > 1 else "单开到"
            parts.append(f"A{n - 1 - i} 的 {' 与 '.join(N(nm) for nm in names)} "
                         f"{verb} A{n - 1 - e}")
    return "；".join(parts) + "。" if parts else "不单开非短途直达列流。"


def build_runtime_stages(p):
    initial = initial_combo(p)
    target = optimal_combo(p)[0]
    path = improvement_path(p, initial, target)
    target_key = canon_combo(target)
    stages = []
    for idx, (combo, meta, delta) in enumerate(path):
        if idx == 0:
            title = "初始方案"
            desc = ("按绝对/必要条件确定初始方案：满足条件的车流单开直达，剩余车流按"
                    "必要条件②合并或随相邻车站开行的列车改编。")
        elif meta is None:
            title = "最佳方案（全枚举最优）"
            desc = "比较全部方案，F耗 最小。"
        else:
            title = f"调整方案 {idx}"
            desc = move_desc(p, meta, delta)
        if idx == len(path) - 1 and canon_combo(combo) == target_key and idx > 0 and meta is not None:
            title = f"调整方案 {idx}（最优）"
        if idx == 0 and canon_combo(combo) == target_key:
            title = "初始方案（即最优方案）"
        stages.append({"title": title, "desc": desc, "combo": combo})
    return stages, target


def validate_runtime_input(key, T, t, Ns):
    base = next((p for p in PROBLEMS if p["key"] == key), None)
    if base is None:
        raise ValueError("未知题目")
    n = base["n"]
    if not isinstance(T, list) or len(T) != n:
        raise ValueError(f"T 集应为长度 {n} 的数组")
    Tf = []
    for x in T:
        try:
            v = float(x)
        except (TypeError, ValueError):
            raise ValueError("T 集必须是数字")
        if not (0 <= v <= 1e6):
            raise ValueError("T 集必须在 0–1000000 之间")
        Tf.append(v)
    if not isinstance(t, dict):
        raise ValueError("t 节必须是对象")
    tf = {}
    for k in base["t"]:
        if str(k) not in t and k not in t:
            raise ValueError("缺少 t 节数据")
        v = float(t.get(str(k), t.get(k)))
        if not (0 < v <= 1e6):
            raise ValueError("t 节必须大于 0")
        tf[int(k)] = v
    if not isinstance(Ns, dict):
        raise ValueError("车流数据必须是对象")
    names = [name for (name, i, j, q) in base["flows"]]
    if set(Ns.keys()) != set(names):
        raise ValueError("车流名称与题目不一致")
    flows = []
    for (name, i, j, q) in base["flows"]:
        v = float(Ns[name])
        if not (0 <= v <= 1e6):
            raise ValueError("车流量必须在 0–1000000 之间")
        flows.append((name, i, j, v))
    for (name, i, j, q) in flows:
        if i < n - 1 and Tf[i] <= 0:
            raise ValueError("有非短途车流的车站 T 集必须大于 0")
    return base, Tf, tf, flows


def runtime_problem(key, T, t, Ns):
    base, Tf, tf, flows = validate_runtime_input(key, T, t, Ns)
    # 默认数据：直接沿用教材定稿的步骤与图
    if (Tf == [float(x) for x in base["T"]] and
            tf == {int(k): float(v) for k, v in base["t"].items()} and
            flows == [(nm, i, j, float(q)) for (nm, i, j, q) in base["flows"]]):
        return base
    p = copy.deepcopy(base)
    p["T"], p["t"], p["flows"] = Tf, tf, flows
    p["runtime"] = True
    p["abs_method"] = (p["n"] == 4)
    p["abs_expect"] = None
    p["abs_opt"] = None
    p["stages"], target = build_runtime_stages(p)
    ev, ts, train, fj = combo_metrics(p, target)
    p["conclusion"] = conclusion_from_combo(p, target)
    p["obj"] = f"F耗 = {ev['cost']:.0f} 车小时；F节 = {fj:.0f} 车小时"
    p["final_text"] = (f"比较全部 {len(all_combos(p))} 个方案，"
                       f"最优 F耗={ev['cost']:.0f}，F节={fj:.0f}。")
    p["merge_text"] = merge_reasoning(p)
    return p


def render_bianzu_panel(key, T, t, Ns):
    p = runtime_problem(key, T, t, Ns)
    return panel_body(p)


# ============================================================ 四、符号与表格
def N(name):
    return f"N<sub>{name}</sub>"


def T_sym(n, i):
    return f"T<sub>集</sub><sup>{n - 1 - i}</sup>"


def t_sym(n, k):
    return f"t<sub>节</sub><sup>{n - 1 - k}</sup>"


def fmt(x):
    return f"{x:g}"


def flow_label(name, q):
    return f"{N(name)}={fmt(q)}"


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
        f"<td>{p['labels'][i]} → {p['labels'][j]}</td><td>{fmt(q)}</td></tr>"
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
    cells = ["<td class='lbl'>T<sub>集</sub></td>"] + [f"<td>{fmt(T[i]) if T[i] else ''}</td>" for i in range(n)]
    rows.append("<tr>" + "".join(cells) + "</tr>")
    cells = ["<td class='lbl'>t<sub>节</sub></td>"] + [f"<td>{fmt(t[i]) if i in t else ''}</td>" for i in range(n)]
    rows.append("<tr>" + "".join(cells) + "</tr>")
    # 车流行
    for (name, i, j, q) in p["flows"]:
        cells = [f"<td colspan='2' class='lbl'>{flow_label(name, q)}</td>"]
        for kk in range(1, n):
            if kk == i:
                cells.append("<td>—</td>")
            elif i < kk < j:
                cells.append(f"<td>{fmt(adapt_by.get((name, kk), 0))}</td>")
            else:
                cells.append("<td></td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    # N改编
    sums = {kk: sum(q for (name, i, j, e, q) in ev["detail"] if e == kk) for kk in range(1, n)}
    cells = ["<td colspan='2' class='lbl'>N<sub>改编</sub></td>"]
    cells += [f"<td>{fmt(sums[kk])}</td>" for kk in range(1, n - 1)] + ["<td></td>"]
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
        cells = [f"<td colspan='2' class='lbl'>{T_sym(n, i)}={fmt(T[i])}</td>",
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
    cells = ["<td class='lbl'>T<sub>集</sub></td>"] + [f"<td>{fmt(T[i]) if T[i] else ''}</td>" for i in range(n)]
    rows.append("<tr>" + "".join(cells) + "</tr>")
    cells = ["<td class='lbl'>t<sub>节</sub></td>"] + [f"<td>{fmt(t[i]) if i in t else ''}</td>" for i in range(n)]
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
                    mark = "△" if name in abs_set else "○"
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
    # ΣN通·t节：所有 ○/△ 记号之和（按站小计，末列总计）
    ts = through_sum(flows, t, ev["through"])
    col = {kk: sum(q * t[kk] for (name, i, j, q) in flows if (name, kk) in ev["through"])
           for kk in range(1, n)}
    cells = ["<td colspan='2' class='lbl'>ΣN<sub>通</sub>·t<sub>节</sub></td>"]
    cells += [f"<td>{fmt(col[kk])}</td>" for kk in range(1, n - 1)]
    cells.append(f"<td><strong>{fmt(ts)}</strong></td>")
    rows.append("<tr>" + "".join(cells) + "</tr>")
    # K 行
    after = n - 2
    for i in range(n - 1):
        if not T[i]:
            continue
        cells = [f"<td colspan='2' class='lbl'>{T_sym(n, i)}={fmt(T[i])}</td>",
                 f"<td colspan='{after}'>K<sub>{n - 1 - i}</sub>={ev['k'][i]}</td>",
                 f"<td>{ev['k'][i] * T[i]:.0f}</td>"]
        rows.append("<tr>" + "".join(cells) + "</tr>")
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
        expr = f"{N(name)}·{t_sym(n, km)} = {fmt(q)}×{fmt(p['t'][km])} = {mn:.0f}"
        if mn >= p["T"][i]:
            abs_lines.append(f"<p>{expr} ≥ {T_sym(n, i)} = {fmt(p['T'][i])}，"
                             f"满足绝对条件，必须单开直达（△）。</p>")
        else:
            abs_lines.append(f"<p>{expr} ＜ {T_sym(n, i)} = {fmt(p['T'][i])}，不满足绝对条件。</p>")
            s = sum(vals)
            ts = "+".join(t_sym(n, k) for k in ks)
            expr2 = (f"{N(name)}·({ts}) = {fmt(q)}×({' + '.join(fmt(p['t'][k]) for k in ks)}) "
                     f"= {s:.0f}")
            if s >= p["T"][i]:
                nec_lines.append(f"<p>{expr2} ≥ {T_sym(n, i)} = {fmt(p['T'][i])}，"
                                 f"满足必要条件①，暂定单开（○）。</p>")
            else:
                nec_lines.append(f"<p>{expr2} ＜ {T_sym(n, i)} = {fmt(p['T'][i])}，"
                                 f"不满足必要条件①，转入（3）判断能否合开。</p>")
    return abs_lines, nec_lines


def stage_stats(p, st):
    combo = stage_combo(p, st)
    ev, ts, train, fj = combo_metrics(p, combo)
    if not p.get("runtime"):
        assert abs(ev["cost"] - st["expect_cost"]) < 1e-6, (p["key"], st["title"], ev["cost"])
        assert abs(fj - st["expect_fj"]) < 1e-6, (p["key"], st["title"], fj)
    if st.get("scheme") and p.get("abs_expect"):
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
    if not p.get("runtime"):
        assert best == p["abs_opt"], (p["key"], best, p["abs_opt"])
    out.append("<h4>第三步，找到车小时消耗最小的方案。</h4>")
    out.append(f"<p>方案{'①②③④⑤⑥⑦⑧⑨⑩'[best-1]} 的 F耗 最小，"
               f"为 {costs[best-1]:.0f} 车小时，为最佳方案。</p>")
    return out


def stage_figure(p, st, caption):
    if st.get("img"):
        return figure(st["img"], caption)
    idx = p.get("_svg_idx", 0) + 1
    p["_svg_idx"] = idx
    svg = draw_scheme.build(diagram_scheme(p, st["combo"]))
    svg = svg.replace('id="ar"', f'id="ar{idx}"').replace("url(#ar)", f"url(#ar{idx})")
    return f"<div class='figure'>{svg}<div class='figcap'>{caption}</div></div>"


def stage_expr(p, st, combo):
    if p["combo_name"] == "4" and "scheme" in st:
        return P4_ORDER[st["scheme"] - 1][2]
    return expr_from_combo(combo, p["n"])


def table_method(p):
    out = ["<h3>表格计算法</h3>",
           "<h4>第 1 步，根据车流量计算所有的 N<sub>通</sub>·t<sub>节</sub> 值，"
           "并填入计算表。</h4>",
           calc_table(p, stage_combo(p, p["stages"][0]), "values")]
    abs_lines, nec_lines = condition_texts(p)
    out += ["<h4>第 2 步，计算绝对条件、必要条件，确定初始方案，并计算目标函数值。</h4>",
            "<h5>（1）绝对条件的判断</h5>", *abs_lines,
            "<h5>（2）必要条件①的判断</h5>", *nec_lines,
            "<h5>（3）必要条件②的判断——剩余车流的合并</h5>",
            f"<p>{p['merge_text']}</p>"]

    # 初始方案
    st = p["stages"][0]
    combo, ev, ts, train, fj, verify = stage_stats(p, st)
    expr = stage_expr(p, st, combo)
    title = st["title"] + (f"（{expr}）" if expr else "")
    out += [f"<h5>{title}</h5>", f"<p>{st['desc']}</p>", calc_table(p, combo),
            stage_figure(p, st, f"{p['title']} · {st['title']}"),
            f"<p class='calc-line'>F<sub>节</sub> = {ts:.0f} − {train:.0f} = {fj:.0f} 车小时。</p>",
            f"<p>{verify}</p>"]
    if st.get("check"):
        out.append(f"<p>{st['check']}</p>")

    out.append("<h4>第 3 步，调整初始方案，使用绝对条件验证方案可行性，"
               "做出计算表格和列车到达站图，然后比较所有调整方案目标函数值。</h4>")
    for st in p["stages"][1:]:
        combo, ev, ts, train, fj, verify = stage_stats(p, st)
        expr = stage_expr(p, st, combo)
        title = st["title"] + (f"（{expr}）" if expr else "")
        out += [f"<h5>{title}</h5>", f"<p>{st['desc']}</p>"]
        if st.get("check"):
            out.append(f"<p>{st['check']}</p>")
        out += [calc_table(p, combo),
                stage_figure(p, st, f"{p['title']} · {st['title']}"),
                f"<p class='calc-line'>F<sub>节</sub> = {ts:.0f} − {train:.0f} = {fj:.0f} 车小时。</p>",
                f"<p>{verify}</p>"]
    out += ["<h4>第 4 步，比较目标函数值，确定最佳方案。</h4>",
            f"<p>{p['final_text']}</p>"]
    return out


def panel_body(p):
    out = [f"<h2>{p['title']} · {p['n']} 个支点站（{p['labels'][0]}–{p['labels'][-1]}）</h2>"]
    if p["abs_method"]:
        out += abs_method(p)
    out += table_method(p)
    out += ["<h3>结论</h3>",
            f"<div class='result-box'><p><strong>最优方案：</strong>{p['conclusion']}</p>"
            f"<p><strong>目标函数值：</strong>{p['obj']}（F节 为相对全改编基线的节省）</p></div>"]
    return "\n".join(out)


def problem_panel(p):
    return (f"<section class='card problem-panel' id='p-{p['key']}' hidden>"
            + panel_body(p) + "</section>")


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
#knownInfo{margin-top:12px}
.known-block{border-top:1px solid #eef0f3;padding-top:10px}
.known-block[hidden]{display:none!important}
.known-title{font-size:15px;color:#1a1a2e;margin:2px 0 8px}
.figure{text-align:center;margin:12px 0 6px}
.figure img{max-width:100%;height:auto;background:#fff;border:1px solid #eee;border-radius:4px;padding:6px}
.figure svg{max-width:100%;height:auto;background:#fff;border:1px solid #eee;border-radius:4px;padding:6px}
.known-block .num-input{width:76px;padding:3px 5px;border:1px solid #d9d9d9;border-radius:4px;font-size:13px;text-align:center}
.bianzu-calc{margin-top:10px}
.bianzu-error{margin-top:6px}
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
  var knowns = Array.prototype.slice.call(document.querySelectorAll('.known-block'));
  var hint = document.getElementById('knownHint');
  var defaults = {};
  panels.forEach(function (p) { defaults[p.id] = p.innerHTML; });

  function show(id) {
    panels.forEach(function (p) {
      p.hidden = (p.id !== id);
      if (p.id === id) p.innerHTML = defaults[p.id];
    });
    knowns.forEach(function (k) {
      k.hidden = (k.dataset.known !== id);
      if (k.dataset.known === id) {
        var f = k.querySelector('form');
        if (f) f.reset();
      }
    });
    btns.forEach(function (b) { b.classList.toggle('active', b.dataset.target === id); });
    if (hint) hint.hidden = true;
  }

  btns.forEach(function (b) {
    b.addEventListener('click', function () { show(b.dataset.target); });
  });

  document.querySelectorAll('.bianzu-form').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var key = form.dataset.key;
      var n = parseInt(form.dataset.n, 10);
      var T = new Array(n).fill(0), t = {}, N = {}, err = null;
      form.querySelectorAll('input[name^="T-"]').forEach(function (inp) {
        var v = parseFloat(inp.value);
        if (!isFinite(v) || v < 0) err = 'T 集与车数必须是非负数';
        T[parseInt(inp.name.slice(2), 10)] = v;
      });
      form.querySelectorAll('input[name^="t-"]').forEach(function (inp) {
        var v = parseFloat(inp.value);
        if (!isFinite(v) || v <= 0) err = 't 节必须大于 0';
        t[inp.name.slice(2)] = v;
      });
      form.querySelectorAll('input[name^="N-"]').forEach(function (inp) {
        var v = parseFloat(inp.value);
        if (!isFinite(v) || v < 0) err = 'T 集与车数必须是非负数';
        N[inp.name.slice(2)] = v;
      });
      var errEl = form.querySelector('.bianzu-error');
      if (err) {
        if (errEl) { errEl.textContent = err; errEl.hidden = false; }
        return;
      }
      if (errEl) errEl.hidden = true;
      try {
        var panel = document.getElementById('p-' + key);
        var base = BZ.get(key);
        if (BZ.isDefault(base, T, t, N)) {
          panel.innerHTML = defaults[panel.id];
        } else {
          panel.innerHTML = BZ.renderPanel(key, T, t, N);
        }
        panels.forEach(function (p) { p.hidden = (p.id !== panel.id); });
        knowns.forEach(function (k) { k.hidden = (k.dataset.known !== panel.id); });
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (ex) {
        if (errEl) { errEl.textContent = ex.message; errEl.hidden = false; }
      }
    });
  });

  var h = location.hash.replace('#', '');
  if (h) {
    var selected = btns.filter(function (b) { return b.dataset.target === h; })[0];
    if (selected) show(h);
  }
})();
"""


RUNTIME_JS = r"""
/* ===== 编组算例：纯前端求解与渲染（file:// 可用） ===== */
var BZ = (function () {
  var DATA = JSON.parse(document.getElementById('bz-data').textContent);
  var BY = {};
  DATA.forEach(function (p) { BY[p.key] = p; });

  function fmt(x) {
    return Math.abs(x - Math.round(x)) < 1e-9 ? String(Math.round(x)) : String(+x.toFixed(4));
  }
  function Nlab(name) { return 'N<sub>' + name + '</sub>'; }
  function Tsym(n, i) { return 'T<sub>集</sub><sup>' + (n - 1 - i) + '</sup>'; }
  function tsym(n, k) { return 't<sub>节</sub><sup>' + (n - 1 - k) + '</sup>'; }
  function minOf(a) { return Math.min.apply(null, a); }
  function sum(a) { var s = 0; a.forEach(function (x) { s += x; }); return s; }

  function partitions(items) {
    if (!items.length) return [[]];
    var first = items[0], rest = items.slice(1), out = [];
    partitions(rest).forEach(function (part) {
      var a = [[first]];
      part.forEach(function (b) { a.push(b.slice()); });
      out.push(a);
      for (var i = 0; i < part.length; i++) {
        var nb = part.map(function (b) { return b.slice(); });
        nb[i] = [first].concat(nb[i]);
        out.push(nb);
      }
    });
    return out;
  }

  function evaluate(n, flows, T, t, combo) {
    var endpoints = combo.map(function (blocks) {
      return new Set(blocks.map(function (b) { return minOf(b); }));
    });
    var k = endpoints.map(function (s, i) {
      var c = 0; s.forEach(function (x) { if (x > i + 1) c++; }); return c;
    });
    var adapt = 0, detail = [], through = new Set();
    flows.forEach(function (f) {
      var name = f[0], i = f[1], j = f[2], q = f[3];
      var block = combo[i].filter(function (b) { return b.indexOf(j) >= 0; })[0];
      var e = minOf(block), adapted = [];
      while (e < j) {
        adapt += q * t[e];
        detail.push({ name: name, i: i, j: j, e: e, N: q });
        adapted.push(e);
        var cand = [];
        endpoints[e].forEach(function (x) { if (x <= j) cand.push(x); });
        cand.push(e + 1);
        e = Math.max.apply(null, cand);
      }
      for (var p = i + 1; p < j; p++) {
        if (adapted.indexOf(p) < 0) through.add(name + '|' + p);
      }
    });
    var train = 0;
    for (var ii = 0; ii < n; ii++) train += k[ii] * T[ii];
    return { cost: adapt + train, adapt: adapt, k: k, detail: detail, through: through };
  }

  function throughSum(flows, t, through) {
    var by = {}; flows.forEach(function (f) { by[f[0]] = f; });
    var s = 0;
    through.forEach(function (key) {
      var a = key.split('|');
      s += by[a[0]][3] * t[a[1]];
    });
    return s;
  }

  function absoluteFlows(n, flows, T, t) {
    var out = new Set();
    flows.forEach(function (f) {
      var name = f[0], i = f[1], j = f[2], q = f[3], vals = [];
      for (var k = i + 1; k < j; k++) vals.push(q * t[k]);
      if (vals.length && Math.min.apply(null, vals) >= T[i]) out.add(name);
    });
    return out;
  }

  function canon(combo) {
    return JSON.stringify(combo.map(function (blocks) {
      return blocks.map(function (b) { return b.slice().sort(function (a, b) { return a - b; }); })
        .sort(function (a, b) { return a[0] - b[0] || a.length - b.length; });
    }));
  }

  function allCombos(n) {
    var dests = [];
    for (var i = 0; i < n; i++) {
      var ds = []; for (var j = i + 1; j < n; j++) ds.push(j);
      dests.push(ds.length ? partitions(ds) : [[]]);
    }
    var combos = [[]];
    dests.forEach(function (parts) {
      var next = [];
      combos.forEach(function (c) {
        parts.forEach(function (part) {
          next.push(c.concat([part.map(function (b) { return b.slice(); })]));
        });
      });
      combos = next;
    });
    return combos;
  }

  function comboMetrics(p, combo) {
    var ev = evaluate(p.n, p.flows, p.T, p.t, combo);
    var ts = throughSum(p.flows, p.t, ev.through);
    var train = 0;
    for (var i = 0; i < p.n; i++) train += ev.k[i] * p.T[i];
    return { ev: ev, ts: ts, train: train, fj: ts - train };
  }

  function initialCombo(p) {
    var n = p.n, T = p.T, t = p.t, byOrigin = {};
    p.flows.forEach(function (f) {
      var i = f[1]; (byOrigin[i] = byOrigin[i] || []).push(f);
    });
    var combo = [];
    for (var i = 0; i < n; i++) {
      if (i === n - 1) { combo.push([]); continue; }
      var here = byOrigin[i] || [], adj = i + 1, fixed = [], rest = [];
      here.forEach(function (f) {
        var name = f[0], j = f[2], q = f[3], vals = [];
        for (var k = i + 1; k < j; k++) vals.push(q * t[k]);
        if (vals.length && (Math.min.apply(null, vals) >= T[i] || sum(vals) >= T[i])) fixed.push(j);
        else rest.push(f);
      });
      var blocks = fixed.sort(function (a, b) { return a - b; }).map(function (j) { return [j]; });
      var restQ = {}; rest.forEach(function (f) { restQ[f[2]] = f[3]; });
      var best = null;
      partitions(Object.keys(restQ).map(Number)).forEach(function (part) {
        var valid = [], invalid = [];
        part.forEach(function (b) {
          var e = minOf(b), sumN = 0, sumt = 0;
          b.forEach(function (j) { sumN += restQ[j]; });
          for (var k = i + 1; k < e; k++) sumt += t[k];
          if (sumN * sumt >= T[i] && sumt > 0) valid.push(b.slice());
          else invalid.push(b.slice());
        });
        var score = [valid.length, -part.length, valid.reduce(function (s, b) { return s + minOf(b); }, 0)];
        var better = false;
        if (!best) better = true;
        else {
          for (var z = 0; z < 3; z++) {
            if (score[z] !== best.score[z]) { better = score[z] > best.score[z]; break; }
          }
        }
        if (better) best = { score: score, valid: valid, invalid: invalid };
      });
      best.valid.forEach(function (b) { blocks.push(b); });
      var loose = [];
      best.invalid.forEach(function (b) { b.forEach(function (j) { loose.push(j); }); });
      loose.sort(function (a, b) { return b - a; });
      var adjBlock = [adj];
      loose.forEach(function (j) {
        var bi = -1, bm = -1;
        blocks.forEach(function (b, idx) {
          var m = minOf(b);
          if (m <= j && (m > bm || (m === bm && idx > bi))) { bm = m; bi = idx; }
        });
        if (bi >= 0) blocks[bi].push(j);
        else adjBlock.push(j);
      });
      blocks.push(adjBlock);
      combo.push(blocks.map(function (b) { return b.slice().sort(function (a, b) { return a - b; }); }));
    }
    return combo;
  }

  function optimalCombo(p) {
    var best = null;
    allCombos(p.n).forEach(function (c) {
      var m = comboMetrics(p, c);
      var key = [m.ev.cost, -m.fj, canon(c)];
      var better = false;
      if (!best) better = true;
      else if (key[0] !== best.key[0]) better = key[0] < best.key[0];
      else if (key[1] !== best.key[1]) better = key[1] < best.key[1];
      else better = key[2] < best.key[2];
      if (better) best = { key: key, combo: c, m: m };
    });
    return best;
  }

  function neighborMoves(p, combo) {
    var n = p.n, baseM = comboMetrics(p, combo), seen = new Set(), out = [];
    for (var i = 0; i < n; i++) {
      combo[i].forEach(function (block, bi) {
        block.forEach(function (d) {
          if (d === i + 1) return;
          var oldMin = minOf(block);
          var base = combo[i].filter(function (_, idx) { return idx !== bi; })
            .map(function (b) { return b.slice(); });
          var old = block.filter(function (x) { return x !== d; });
          var variants = [];
          variants.push(base.concat(old.length ? [old.slice()] : []).concat([[d]]));
          base.forEach(function (b, bj) {
            if (minOf(b) <= d) {
              var v = base.map(function (x) { return x.slice(); });
              v[bj] = b.concat([d]);
              if (old.length) v.push(old.slice());
              variants.push(v);
            }
          });
          if (!base.some(function (b) { return b.indexOf(i + 1) >= 0; })) {
            variants.push(base.concat(old.length ? [old.slice()] : []).concat([[i + 1, d]]));
          }
          variants.forEach(function (blocks) {
            var nc = combo.map(function (bs, si) {
              if (si !== i) return bs.map(function (b) { return b.slice(); });
              return blocks.filter(function (b) { return b.length; })
                .map(function (b) { return b.slice().sort(function (a, b) { return a - b; }); });
            });
            var ck = canon(nc);
            if (seen.has(ck)) return;
            seen.add(ck);
            var m = comboMetrics(p, nc);
            if (m.fj <= baseM.fj + 1e-9) return;
            var nb = nc[i].filter(function (b) { return b.indexOf(d) >= 0; })[0];
            out.push({ combo: nc, meta: { i: i, d: d, oldMin: oldMin, newMin: minOf(nb) },
                       delta: m.fj - baseM.fj });
          });
        });
      });
    }
    return out;
  }

  function improvementPath(p, start, target) {
    var sk = canon(start), tk = canon(target);
    if (sk === tk) return [{ combo: start, meta: null, delta: 0 }];
    var info = {}; info[sk] = { combo: start, parent: null, meta: null, delta: 0 };
    var q = [sk];
    while (q.length) {
      var ck = q.shift(), cur = info[ck].combo;
      var moves = neighborMoves(p, cur);
      for (var mi = 0; mi < moves.length; mi++) {
        var mv = moves[mi], nk = canon(mv.combo);
        if (info[nk]) continue;
        info[nk] = { combo: mv.combo, parent: ck, meta: mv.meta, delta: mv.delta };
        if (nk === tk) {
          var path = [], kk = nk;
          while (kk !== null) {
            var it = info[kk];
            path.push({ combo: it.combo, meta: it.meta, delta: it.delta });
            kk = it.parent;
          }
          return path.reverse();
        }
        q.push(nk);
      }
    }
    var path2 = [{ combo: start, meta: null, delta: 0 }], cur2 = start;
    while (true) {
      var ms = neighborMoves(p, cur2);
      if (!ms.length) break;
      ms.sort(function (a, b) { return b.delta - a.delta; });
      path2.push(ms[0]);
      cur2 = ms[0].combo;
    }
    if (canon(cur2) !== tk) path2.push({ combo: target, meta: null, delta: 0 });
    return path2;
  }

  function exprFromCombo(combo, n) {
    var out = [];
    combo.forEach(function (blocks) {
      if (!blocks.length) return;
      var groups = blocks.map(function (b) {
        return b.map(function (x) { return n - 1 - x; }).sort(function (a, b) { return a - b; })
          .join('+');
      });
      groups.sort(function (a, b) {
        var fa = parseInt(a.split('+')[0], 10), fb = parseInt(b.split('+')[0], 10);
        return fa - fb || a.length - b.length;
      });
      out.push(groups.join(','));
    });
    return out.join('; ');
  }

  function moveDesc(p, meta, delta) {
    var i = meta.i, d = meta.d, oldMin = meta.oldMin, newMin = meta.newMin;
    var f = p.flows.filter(function (x) { return x[1] === i && x[2] === d; })[0];
    var n = p.n, aOld = 'A' + (n - 1 - oldMin), aNew = 'A' + (n - 1 - newMin);
    if (oldMin === newMin) {
      return Nlab(f[0]) + ' 改换编组去向（终点仍为 ' + aNew + '），F节 增加 ' + delta.toFixed(0) + ' 车小时。';
    }
    return '压缩 ' + Nlab(f[0]) + ' 的到站/发站：由终点 ' + aOld + ' 改为 ' + aNew +
      '，F节 增加 ' + delta.toFixed(0) + ' 车小时。';
  }

  function remainingFlows(p) {
    var out = [];
    p.flows.forEach(function (f) {
      var vals = [];
      for (var k = f[1] + 1; k < f[2]; k++) vals.push(f[3] * p.t[k]);
      if (!vals.length) return;
      if (minOf(vals) >= p.T[f[1]] || sum(vals) >= p.T[f[1]]) return;
      out.push(f);
    });
    return out;
  }

  function mergeReasoning(p) {
    var n = p.n, rem = remainingFlows(p);
    if (!rem.length) return '（1）（2）已确定全部车流的编组方式，没有剩余车流需要合并。';
    var names = rem.map(function (f) { return Nlab(f[0]); }).join('、');
    var parts = [rem.length > 1
      ? '（1）（2）均不满足的剩余车流为 ' + names + '。'
      : '（1）（2）均不满足的剩余车流只有 ' + names + '。'];
    var combo = initialCombo(p), seen = {};
    rem.forEach(function (f) {
      var i = f[1], j = f[2];
      var blk = combo[i].filter(function (b) { return b.indexOf(j) >= 0; })[0];
      var e = minOf(blk), key = i + '|' + blk.join(',');
      if (e <= i + 1 || seen[key]) return;
      seen[key] = 1;
      var group = p.flows.filter(function (g) { return g[1] === i && blk.indexOf(g[2]) >= 0; });
      var sumN = 0; group.forEach(function (g) { sumN += g[3]; });
      var sumt = 0; for (var k = i + 1; k < e; k++) sumt += p.t[k];
      var saving = sumN * sumt, ok = saving >= p.T[i];
      parts.push('A' + (n - 1 - i) + ' 的 ' +
        group.map(function (g) { return Nlab(g[0]); }).join('、') +
        ' 合并开往 A' + (n - 1 - e) + '：ΣN＝' + fmt(sumN) + '，无改编通过沿途支点站的节省 ' +
        fmt(sumN) + '×' + fmt(sumt) + '＝' + fmt(saving) + (ok ? ' ≥ ' : ' ＜ ') +
        'T集＝' + fmt(p.T[i]) + '，' + (ok ? '满足' : '不满足') + '必要条件②。');
    });
    var adj = [];
    rem.forEach(function (f) {
      var blk = combo[f[1]].filter(function (b) { return b.indexOf(f[2]) >= 0; })[0];
      if (minOf(blk) <= f[1] + 1) adj.push(Nlab(f[0]));
    });
    if (adj.length) {
      parts.push(adj.join('、') + ' 只能随相邻车站开行的列车改编走行，形成不了非短途直达列流。');
    }
    parts.push('初始方案为 ' + exprFromCombo(combo, n) + '。');
    return parts.join('');
  }

  function conclusionFromCombo(p, combo) {
    var n = p.n, parts = [];
    combo.forEach(function (blocks, i) {
      blocks.forEach(function (blk) {
        var e = minOf(blk);
        if (e - i < 2) return;
        var names = p.flows.filter(function (g) {
          return g[1] === i && blk.indexOf(g[2]) >= 0;
        }).map(function (g) { return Nlab(g[0]); });
        if (!names.length) return;
        parts.push('A' + (n - 1 - i) + ' 的 ' + names.join(' 与 ') +
          (names.length > 1 ? ' 合开到 ' : ' 单开到 ') + 'A' + (n - 1 - e));
      });
    });
    return parts.length ? parts.join('；') + '。' : '不单开非短途直达列流。';
  }

  function buildRuntimeStages(p) {
    var initial = initialCombo(p);
    var target = optimalCombo(p).combo;
    var path = improvementPath(p, initial, target);
    var tk = canon(target), stages = [];
    path.forEach(function (item, idx) {
      var title, desc;
      if (idx === 0) {
        title = '初始方案';
        desc = '按绝对/必要条件确定初始方案：满足条件的车流单开直达，剩余车流按必要条件②合并或随相邻车站开行的列车改编。';
      } else if (!item.meta) {
        title = '最佳方案（全枚举最优）';
        desc = '比较全部方案，F耗 最小。';
      } else {
        title = '调整方案 ' + idx;
        desc = moveDesc(p, item.meta, item.delta);
      }
      if (idx === path.length - 1 && canon(item.combo) === tk && idx > 0 && item.meta) {
        title = '调整方案 ' + idx + '（最优）';
      }
      if (idx === 0 && canon(item.combo) === tk) title = '初始方案（即最优方案）';
      stages.push({ title: title, desc: desc, combo: item.combo });
    });
    return { stages: stages, target: target };
  }

  /* ---------- 到达站图 ---------- */
  function diagramScheme(p, combo) {
    var n = p.n;
    var endpoints = combo.map(function (blocks) {
      return new Set(blocks.map(function (b) { return minOf(b); }));
    });
    var legs = {};
    function addLeg(m, e, origin, name) {
      var key = m + ',' + e;
      (legs[key] = legs[key] || []).push([origin, name]);
    }
    p.flows.forEach(function (f) {
      var name = f[0], i = f[1], j = f[2];
      var m = i;
      var block = combo[m].filter(function (b) { return b.indexOf(j) >= 0; })[0];
      var e = minOf(block);
      while (true) {
        addLeg(m, e, i, name);
        if (e >= j) break;
        m = e;
        var cand = [];
        endpoints[m].forEach(function (x) { if (x <= j) cand.push(x); });
        cand.push(m + 1);
        e = Math.max.apply(null, cand);
      }
    });
    for (var i = 0; i < n - 1; i++) addLeg(i, i + 1, i, '' + (n - 1 - i) + (n - 2 - i));
    var items = [];
    Object.keys(legs).forEach(function (key) {
      var a = key.split(','), m = +a[0], e = +a[1];
      var labels = legs[key].slice().sort(function (x, y) {
        return x[0] - y[0] || (x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0);
      });
      var seen = {}, terms = [];
      labels.forEach(function (l) { if (!seen[l[1]]) { seen[l[1]] = 1; terms.push(l[1]); } });
      items.push({ from: m, to: e, terms: terms });
    });
    var units = items.filter(function (x) { return x.to === x.from + 1; })
      .sort(function (a, b) { return a.from - b.from; });
    var directs = items.filter(function (x) { return x.to > x.from + 1; })
      .sort(function (a, b) { return a.from - b.from || b.to - a.to; });
    var chainRow = directs.length, lines = [];
    directs.forEach(function (x, r) {
      lines.push({ row: r, from: x.from, to: x.to, terms: x.terms });
    });
    units.forEach(function (x) {
      lines.push({ row: chainRow, from: x.from, to: x.to, terms: x.terms });
    });
    return { lines: lines, n: n };
  }

  var FONT = 'Times New Roman, Times, Liberation Serif, DejaVu Serif, serif';

  function svgExpr(x, y, terms) {
    var size = 23, sub = 14, dy = 5.5, parts = [];
    terms.forEach(function (t, i) {
      if (i) parts.push('<tspan font-style="normal">+</tspan>');
      parts.push('<tspan font-style="italic">N</tspan>' +
        '<tspan font-size="' + sub + '" dy="' + dy + '" font-style="normal">' + t + '</tspan>' +
        '<tspan dy="-5.5"> </tspan>');
    });
    return '<text x="' + x.toFixed(1) + '" y="' + y + '" font-family="' + FONT +
      '" font-size="' + size + '" text-anchor="start" fill="#000">' + parts.join('') + '</text>';
  }

  function buildSVG(scheme, idx) {
    var W = 950, x0 = 80, dx = 212, rightPad = 40, topPad = 95, gap = 80, bottom = 85;
    var n = scheme.n;
    dx = Math.min(dx, (W - x0 - rightPad) / (n - 1));
    var xs = []; for (var i = 0; i < n; i++) xs.push(x0 + i * dx);
    var maxRow = 0; scheme.lines.forEach(function (l) { maxRow = Math.max(maxRow, l.row); });
    var h = topPad + maxRow * gap + bottom;
    var ys = []; for (var r = 0; r <= maxRow; r++) ys.push(topPad + r * gap);
    var out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + h +
      '" width="' + W + '" height="' + h + '">',
      '  <defs>',
      '    <marker id="ar' + idx + '" viewBox="0 0 10 10" refX="9.5" refY="5" ' +
      'markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto-start-reverse">',
      '      <path d="M0,1.2 L10,5 L0,8.8 z" fill="#000"/>',
      '    </marker>',
      '  </defs>',
      '  <rect x="0" y="0" width="' + W + '" height="' + h + '" fill="#ffffff"/>'];
    scheme.lines.forEach(function (l) {
      var x1 = xs[l.from], x2 = xs[l.to], y = ys[l.row];
      out.push('  <line x1="' + x1.toFixed(1) + '" y1="' + y + '" x2="' + x2.toFixed(1) +
        '" y2="' + y + '" stroke="#000" stroke-width="2.2" marker-end="url(#ar' + idx + ')"/>');
      out.push('  <line x1="' + x1.toFixed(1) + '" y1="' + (y - 11) + '" x2="' + x1.toFixed(1) +
        '" y2="' + (y + 11) + '" stroke="#000" stroke-width="2.2"/>');
      out.push(svgExpr(x1 + 4, y - 14, l.terms));
    });
    var yLast = ys[maxRow];
    for (var s = 0; s < n; s++) {
      out.push('  <text x="' + xs[s].toFixed(1) + '" y="' + (yLast + 30) +
        '" font-family="' + FONT + '" font-size="23" text-anchor="middle" fill="#000">' +
        (n - 1 - s) + '</text>');
    }
    out.push('</svg>');
    return out.join('\n');
  }

  /* ---------- 表格 ---------- */
  var P4_A3 = { sep: [[1], [2], [3]], m12: [[1, 2], [3]], m01: [[1], [2, 3]],
                m02: [[1, 3], [2]], all: [[1, 2, 3]] };
  var P4_A2 = { sep: [[2], [3]], all: [[2, 3]] };
  var P4_ORDER = [
    ['sep', 'sep', '0,1,2; 0,1; 0'], ['m12', 'sep', '0,1+2; 0,1; 0'],
    ['m01', 'sep', '0+1,2; 0,1; 0'], ['m02', 'sep', '0+2,1; 0,1; 0'],
    ['all', 'sep', '0+1+2; 0,1; 0'], ['sep', 'all', '0,1,2; 0+1; 0'],
    ['m12', 'all', '0,1+2; 0+1; 0'], ['m01', 'all', '0+1,2; 0+1; 0'],
    ['m02', 'all', '0+2,1; 0+1; 0'], ['all', 'all', '0+1+2; 0+1; 0']
  ];
  function combo4(a3, a2) {
    return [P4_A3[a3].map(function (b) { return b.slice(); }),
            P4_A2[a2].map(function (b) { return b.slice(); }), [[3]], []];
  }
  function tableScroll(html) { return "<div class='table-scroll'>" + html + '</div>'; }
  function headRow(p) {
    return '<tr><th></th>' + p.labels.map(function (s) { return '<th>' + s + '</th>'; }).join('') + '</tr>';
  }

  function schemeTable(p, k) {
    var n = p.n, combo = combo4(P4_ORDER[k - 1][0], P4_ORDER[k - 1][1]);
    var ev = evaluate(n, p.flows, p.T, p.t, combo), adaptBy = {};
    ev.detail.forEach(function (d) {
      var key = d.name + '|' + d.e;
      adaptBy[key] = (adaptBy[key] || 0) + d.N;
    });
    var rows = [];
    var cells = ["<td class='lbl'>T<sub>集</sub></td>"];
    for (var i = 0; i < n; i++) cells.push('<td>' + (p.T[i] ? fmt(p.T[i]) : '') + '</td>');
    rows.push('<tr>' + cells.join('') + '</tr>');
    cells = ["<td class='lbl'>t<sub>节</sub></td>"];
    for (i = 0; i < n; i++) cells.push('<td>' + (p.t[i] !== undefined ? fmt(p.t[i]) : '') + '</td>');
    rows.push('<tr>' + cells.join('') + '</tr>');
    p.flows.forEach(function (f) {
      var name = f[0], i = f[1], j = f[2], q = f[3];
      var cs = ["<td colspan='2' class='lbl'>" + Nlab(name) + '=' + fmt(q) + '</td>'];
      for (var kk = 1; kk < n; kk++) {
        if (kk === i) cs.push('<td>—</td>');
        else if (i < kk && kk < j) cs.push('<td>' + fmt(adaptBy[name + '|' + kk] || 0) + '</td>');
        else cs.push('<td></td>');
      }
      rows.push('<tr>' + cs.join('') + '</tr>');
    });
    var sums = {};
    ev.detail.forEach(function (d) { sums[d.e] = (sums[d.e] || 0) + d.N; });
    cells = ["<td colspan='2' class='lbl'>N<sub>改编</sub></td>"];
    for (i = 1; i < n - 1; i++) cells.push('<td>' + fmt(sums[i] || 0) + '</td>');
    cells.push('<td></td>');
    rows.push('<tr>' + cells.join('') + '</tr>');
    cells = ["<td colspan='2' class='lbl'>N<sub>改编</sub>·t<sub>节</sub></td>"];
    for (i = 1; i < n - 1; i++) cells.push('<td>' + (sums[i] || 0) * p.t[i] + '</td>');
    cells.push('<td>' + fmt(ev.adapt) + '</td>');
    rows.push('<tr>' + cells.join('') + '</tr>');
    for (i = 0; i < n - 1; i++) {
      if (!p.T[i]) continue;
      rows.push("<tr><td colspan='2' class='lbl'>" + Tsym(n, i) + '=' + fmt(p.T[i]) +
        "</td><td colspan='" + (n - 2) + "'>K<sub>" + (n - 1 - i) + '</sub>=' + ev.k[i] +
        '</td><td>' + fmt(ev.k[i] * p.T[i]) + '</td></tr>');
    }
    var terms = [fmt(ev.adapt)];
    for (i = 0; i < n - 1; i++) if (p.T[i]) terms.push(fmt(ev.k[i] * p.T[i]));
    rows.push("<tr><td colspan='" + n + "' class='lbl'>F<sub>耗</sub></td><td><strong>" +
      terms.join('+') + '=' + fmt(ev.cost) + '</strong></td></tr>');
    return tableScroll('<table class="plan-table calc-table"><thead>' + headRow(p) +
      '</thead><tbody>' + rows.join('') + '</tbody></table>');
  }

  function calcTable(p, combo, mode) {
    var n = p.n, ev = evaluate(n, p.flows, p.T, p.t, combo);
    var absSet = absoluteFlows(n, p.flows, p.T, p.t);
    var rows = [];
    var cells = ["<td class='lbl'>T<sub>集</sub></td>"];
    for (var i = 0; i < n; i++) cells.push('<td>' + (p.T[i] ? fmt(p.T[i]) : '') + '</td>');
    rows.push('<tr>' + cells.join('') + '</tr>');
    cells = ["<td class='lbl'>t<sub>节</sub></td>"];
    for (i = 0; i < n; i++) cells.push('<td>' + (p.t[i] !== undefined ? fmt(p.t[i]) : '') + '</td>');
    rows.push('<tr>' + cells.join('') + '</tr>');
    p.flows.forEach(function (f) {
      var name = f[0], i = f[1], j = f[2], q = f[3];
      var cs = ["<td colspan='2' class='lbl'>" + Nlab(name) + '=' + fmt(q) + '</td>'];
      for (var kk = 1; kk < n; kk++) {
        if (kk === i) cs.push('<td>—</td>');
        else if (i < kk && kk < j) {
          var val = q * p.t[kk];
          if (mode === 'values') cs.push('<td>' + val.toFixed(0) + '</td>');
          else if (ev.through.has(name + '|' + kk)) {
            var mark = absSet.has(name) ? '△' : '○';
            var cls = mark === '△' ? 'mark-t' : 'mark-o';
            cs.push('<td>' + val.toFixed(0) + '<span class="' + cls + '">' + mark + '</span></td>');
          } else cs.push("<td class='muted'>" + val.toFixed(0) + '</td>');
        } else cs.push('<td></td>');
      }
      rows.push('<tr>' + cs.join('') + '</tr>');
    });
    if (mode === 'values') {
      return tableScroll('<table class="plan-table calc-table"><thead>' + headRow(p) +
        '</thead><tbody>' + rows.join('') + '</tbody></table>');
    }
    var ts = throughSum(p.flows, p.t, ev.through);
    var col = {};
    for (i = 1; i < n; i++) col[i] = 0;
    p.flows.forEach(function (f) {
      for (var kk = f[1] + 1; kk < f[2]; kk++)
        if (ev.through.has(f[0] + '|' + kk)) col[kk] += f[3] * p.t[kk];
    });
    cells = ["<td colspan='2' class='lbl'>ΣN<sub>通</sub>·t<sub>节</sub></td>"];
    for (i = 1; i < n - 1; i++) cells.push('<td>' + fmt(col[i]) + '</td>');
    cells.push('<td><strong>' + fmt(ts) + '</strong></td>');
    rows.push('<tr>' + cells.join('') + '</tr>');
    for (i = 0; i < n - 1; i++) {
      if (!p.T[i]) continue;
      rows.push("<tr><td colspan='2' class='lbl'>" + Tsym(n, i) + '=' + fmt(p.T[i]) +
        "</td><td colspan='" + (n - 2) + "'>K<sub>" + (n - 1 - i) + '</sub>=' + ev.k[i] +
        '</td><td>' + fmt(ev.k[i] * p.T[i]) + '</td></tr>');
    }
    var train = 0; for (i = 0; i < n; i++) train += ev.k[i] * p.T[i];
    rows.push("<tr><td colspan='" + n + "' class='lbl'>F<sub>节</sub></td><td><strong>" +
      ts.toFixed(0) + '−' + train.toFixed(0) + '=' + (ts - train).toFixed(0) +
      '</strong></td></tr>');
    return tableScroll('<table class="plan-table calc-table"><thead>' + headRow(p) +
      '</thead><tbody>' + rows.join('') + '</tbody></table>');
  }

  function conditionTexts(p) {
    var n = p.n, absLines = [], necLines = [];
    p.flows.forEach(function (f) {
      var name = f[0], i = f[1], j = f[2], q = f[3], ks = [], vals = [];
      for (var k = i + 1; k < j; k++) { ks.push(k); vals.push(q * p.t[k]); }
      var mn = Math.min.apply(null, vals), km = ks[vals.indexOf(mn)];
      var expr = Nlab(name) + '·' + tsym(n, km) + ' = ' + fmt(q) + '×' + fmt(p.t[km]) +
        ' = ' + mn.toFixed(0);
      if (mn >= p.T[i]) {
        absLines.push('<p>' + expr + ' ≥ ' + Tsym(n, i) + ' = ' + fmt(p.T[i]) +
          '，满足绝对条件，必须单开直达（△）。</p>');
      } else {
        absLines.push('<p>' + expr + ' ＜ ' + Tsym(n, i) + ' = ' + fmt(p.T[i]) +
          '，不满足绝对条件。</p>');
        var s = sum(vals);
        var ts = ks.map(function (k) { return tsym(n, k); }).join('+');
        var expr2 = Nlab(name) + '·(' + ts + ') = ' + fmt(q) + '×(' +
          ks.map(function (k) { return fmt(p.t[k]); }).join(' + ') + ') = ' + s.toFixed(0);
        if (s >= p.T[i]) {
          necLines.push('<p>' + expr2 + ' ≥ ' + Tsym(n, i) + ' = ' + fmt(p.T[i]) +
            '，满足必要条件①，暂定单开（○）。</p>');
        } else {
          necLines.push('<p>' + expr2 + ' ＜ ' + Tsym(n, i) + ' = ' + fmt(p.T[i]) +
            '，不满足必要条件①，转入（3）判断能否合开。</p>');
        }
      }
    });
    return { abs: absLines, nec: necLines };
  }

  function figureImg(src, caption) {
    return "<div class='figure'><img src='" + src + "' alt='" + caption +
      "'><div class='figcap'>" + caption + '</div></div>';
  }
  function figureSvg(svg, caption) {
    return "<div class='figure'>" + svg + "<div class='figcap'>" + caption + '</div></div>';
  }

  function stageFigure(p, st, ctx, caption) {
    ctx.svg += 1;
    var scheme = diagramScheme(p, st.combo);
    return figureSvg(buildSVG(scheme, ctx.svg), caption);
  }

  function stageStats(p, st) {
    var combo = st.combo, m = comboMetrics(p, combo);
    var c = 0;
    p.flows.forEach(function (f) {
      var q = f[3], s = 0;
      for (var k = f[1] + 1; k < f[2]; k++) s += p.t[k];
      c += q * s;
    });
    var verify = '用全改编基线验证：C − F耗 = ' + c.toFixed(0) + ' − ' + m.ev.cost.toFixed(0) +
      ' = ' + m.fj.toFixed(0) + ' = F节。';
    return { combo: combo, m: m, verify: verify };
  }

  function absMethod(p) {
    var out = ['<h3>绝对计算法</h3>',
      '<h4>第一步，枚举所有方案，画出列车到达站图。</h4>',
      '<p>' + p.n + ' 个支点站方向共 10 个编组方案，逐方案计算如下。</p>',
      '<h4>第二步，列出绝对计算法表格：明确非短途直达车流的量，根据到站图填写' +
      '直达车流无改编通过的量为 0，剩余为车流量，并计算改编车小时、集结车小时与目标函数值。</h4>'];
    var costs = [];
    for (var k = 1; k <= 10; k++) {
      var combo = combo4(P4_ORDER[k - 1][0], P4_ORDER[k - 1][1]);
      costs.push(evaluate(p.n, p.flows, p.T, p.t, combo).cost);
      out.push("<div class='scheme-block'><h5>方案" + '①②③④⑤⑥⑦⑧⑨⑩'[k - 1] + '（' +
        P4_ORDER[k - 1][2] + '）</h5>');
      out.push(figureImg('svg/bianzu/11.9.' + k + '.svg',
        '方案' + '①②③④⑤⑥⑦⑧⑨⑩'[k - 1] + '的列车到达站图'));
      out.push(schemeTable(p, k));
      out.push('</div>');
    }
    var bi = 0;
    for (var z = 1; z < costs.length; z++) if (costs[z] < costs[bi]) bi = z;
    out.push('<h4>第三步，找到车小时消耗最小的方案。</h4>');
    out.push('<p>方案' + '①②③④⑤⑥⑦⑧⑨⑩'[bi] + ' 的 F耗 最小，为 ' +
      costs[bi].toFixed(0) + ' 车小时，为最佳方案。</p>');
    return out;
  }

  function tableMethod(p, ctx) {
    var out = ['<h3>表格计算法</h3>',
      '<h4>第 1 步，根据车流量计算所有的 N<sub>通</sub>·t<sub>节</sub> 值，并填入计算表。</h4>',
      calcTable(p, p.stages[0].combo, 'values')];
    var cond = conditionTexts(p);
    out = out.concat(['<h4>第 2 步，计算绝对条件、必要条件，确定初始方案，并计算目标函数值。</h4>',
      '<h5>（1）绝对条件的判断</h5>'], cond.abs,
      ['<h5>（2）必要条件①的判断</h5>'], cond.nec,
      ['<h5>（3）必要条件②的判断——剩余车流的合并</h5>', '<p>' + p.merge_text + '</p>']);
    var st = p.stages[0], info = stageStats(p, st);
    out = out.concat(['<h5>' + st.title + '（' + exprFromCombo(st.combo, p.n) + '）</h5>',
      '<p>' + st.desc + '</p>', calcTable(p, st.combo),
      stageFigure(p, st, ctx, p.title + ' · ' + st.title),
      "<p class='calc-line'>F<sub>节</sub> = " + info.m.ts.toFixed(0) + ' − ' +
      info.m.train.toFixed(0) + ' = ' + info.m.fj.toFixed(0) + ' 车小时。</p>',
      '<p>' + info.verify + '</p>']);
    out.push('<h4>第 3 步，调整初始方案，使用绝对条件验证方案可行性，' +
      '做出计算表格和列车到达站图，然后比较所有调整方案目标函数值。</h4>');
    for (var i = 1; i < p.stages.length; i++) {
      st = p.stages[i]; info = stageStats(p, st);
      out = out.concat(['<h5>' + st.title + '（' + exprFromCombo(st.combo, p.n) + '）</h5>',
        '<p>' + st.desc + '</p>', calcTable(p, st.combo),
        stageFigure(p, st, ctx, p.title + ' · ' + st.title),
        "<p class='calc-line'>F<sub>节</sub> = " + info.m.ts.toFixed(0) + ' − ' +
        info.m.train.toFixed(0) + ' = ' + info.m.fj.toFixed(0) + ' 车小时。</p>',
        '<p>' + info.verify + '</p>']);
    }
    out.push('<h4>第 4 步，比较目标函数值，确定最佳方案。</h4>');
    out.push('<p>' + p.final_text + '</p>');
    return out;
  }

  function panelBody(p) {
    var out = ['<h2>' + p.title + ' · ' + p.n + ' 个支点站（' + p.labels[0] + '–' +
      p.labels[p.n - 1] + '）</h2>'];
    if (p.n === 4) out = out.concat(absMethod(p));
    var ctx = { svg: 0 };
    out = out.concat(tableMethod(p, ctx));
    out = out.concat(['<h3>结论</h3>',
      "<div class='result-box'><p><strong>最优方案：</strong>" + p.conclusion +
      '</p><p><strong>目标函数值：</strong>' + p.obj +
      '（F节 为相对全改编基线的节省）</p></div>']);
    return out.join('\n');
  }

  function isDefault(base, T, t, Ns) {
    for (var i = 0; i < base.n; i++) if (Math.abs(T[i] - base.T[i]) > 1e-9) return false;
    for (var k in base.t) {
      if (!(k in t) || Math.abs(t[k] - base.t[k]) > 1e-9) return false;
    }
    for (var z = 0; z < base.flows.length; z++) {
      var f = base.flows[z];
      if (!(f[0] in Ns) || Math.abs(Ns[f[0]] - f[3]) > 1e-9) return false;
    }
    return true;
  }

  function runtimePanel(key, T, t, Ns) {
    var base = BY[key];
    var p = JSON.parse(JSON.stringify(base));
    p.T = T.slice();
    p.t = {}; for (var k in t) p.t[k] = t[k];
    p.flows = base.flows.map(function (f) { return [f[0], f[1], f[2], Ns[f[0]]]; });
    var built = buildRuntimeStages(p);
    p.stages = built.stages;
    var target = built.target;
    var m = comboMetrics(p, target);
    p.conclusion = conclusionFromCombo(p, target);
    p.obj = 'F耗 = ' + m.ev.cost.toFixed(0) + ' 车小时；F节 = ' + m.fj.toFixed(0) + ' 车小时';
    p.final_text = '比较全部 ' + allCombos(p.n).length + ' 个方案，最优 F耗=' +
      m.ev.cost.toFixed(0) + '，F节=' + m.fj.toFixed(0) + '。';
    p.merge_text = mergeReasoning(p);
    return panelBody(p);
  }

  return {
    get: function (key) { return BY[key]; },
    isDefault: isDefault,
    renderPanel: runtimePanel
  };
})();
"""


def edit_form(p):
    n = p["n"]
    labels = p["labels"]
    head = "".join(f"<th>{s}</th>" for s in labels)
    T_cells, t_cells = [], []
    for i in range(n):
        if p["T"][i]:
            T_cells.append(f"<td><input class='num-input' type='text' inputmode='numeric' "
                           f"name='T-{i}' value='{p['T'][i]:g}'></td>")
        else:
            T_cells.append("<td></td>")
        if i in p["t"]:
            t_cells.append(f"<td><input class='num-input' type='text' inputmode='decimal' "
                           f"name='t-{i}' value='{p['t'][i]:g}'></td>")
        else:
            t_cells.append("<td></td>")
    main = (f"<div class='table-scroll'><table class='plan-table'>"
            f"<thead><tr><th>项目</th>{head}</tr></thead><tbody>"
            f"<tr><td class='lbl'>T<sub>集</sub></td>{''.join(T_cells)}</tr>"
            f"<tr><td class='lbl'>t<sub>节</sub></td>{''.join(t_cells)}</tr>"
            f"</tbody></table></div>")
    flow_rows = "".join(
        f"<tr><td class='lbl'>{N(name)}</td>"
        f"<td>{labels[i]} → {labels[j]}</td>"
        f"<td><input class='num-input' type='text' inputmode='numeric' "
        f"name='N-{name}' value='{q:g}'></td></tr>"
        for (name, i, j, q) in p["flows"])
    flows = (f"<div class='table-scroll'><table class='plan-table'>"
             f"<thead><tr><th>车流</th><th>径路</th><th>车数</th></tr></thead>"
             f"<tbody>{flow_rows}</tbody></table></div>")
    return (f"<form class='bianzu-form' data-key='{p['key']}' data-n='{n}'>"
            + main + flows +
            f"<button type='submit' class='btn btn-primary bianzu-calc'>计算列车编组计划</button>"
            f"<p class='error-msg bianzu-error' hidden></p></form>")


def selector_card():
    def button(p):
        label = p["title"].replace(" ", "")
        return (f"<button type='button' class='btn-sm preset problem-btn' "
                f"data-target='p-{p['key']}'>{label}</button>")

    def known(p):
        return (f"<div class='known-block' data-known='p-{p['key']}' hidden>"
                f"<h3 class='known-title'>{p['title']} · 已知信息</h3>"
                + edit_form(p) +
                f"<p class='note'>{p['note']}</p></div>")

    ex = [p for p in PROBLEMS if p["key"].startswith("ex")]
    xt = [p for p in PROBLEMS if p["key"].startswith("xt")]
    return (f"<section class='card' id='selector'><h2>选择算例</h2>"
            f"<div class='preset-row'>"
            f"<span class='preset-label'>例题：</span>"
            + "".join(button(p) for p in ex) +
            f"<span class='preset-label' style='margin-left:12px'>习题：</span>"
            + "".join(button(p) for p in xt) +
            f"</div>"
            f"<div id='knownInfo'>"
            f"<p class='note' id='knownHint'>点击上方题目按钮，查看该题的已知信息"
            f"（T<sub>集</sub>、t<sub>节</sub>、非短途车流）与完整计算过程。</p>"
            + "".join(known(p) for p in PROBLEMS) +
            f"</div></section>")


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

    # ---------- 通用求解器回归：默认数据应复现教材初始/最优 ----------
    for base in PROBLEMS:
        p = copy.deepcopy(base)
        p["runtime"] = True
        p["abs_method"] = (p["n"] == 4)
        p["abs_expect"] = None
        p["abs_opt"] = None
        init = initial_combo(p)
        default_init = stage_combo(base, base["stages"][0])
        assert canon_combo(init) == canon_combo(default_init), (
            base["key"], init, default_init)
        target = optimal_combo(p)[0]
        cost = combo_metrics(p, target)[0]["cost"]
        if base.get("abs_expect"):
            expected = min(base["abs_expect"])
        else:
            expected = next(s for s in base["stages"] if s["opt"])["expect_cost"]
        assert abs(cost - expected) < 1e-6, (base["key"], cost, expected)
        stages, tgt = build_runtime_stages(p)
        assert canon_combo(tgt) == canon_combo(target)
        assert stages and canon_combo(stages[-1]["combo"]) == canon_combo(target)

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
    data_json = json.dumps([{
        "key": p["key"], "title": p["title"], "n": p["n"], "labels": p["labels"],
        "T": [float(x) for x in p["T"]],
        "t": {str(k): float(v) for k, v in p["t"].items()},
        "flows": [[nm, i, j, float(q)] for (nm, i, j, q) in p["flows"]],
        "abs_method": p["abs_method"], "note": p["note"],
    } for p in PROBLEMS], ensure_ascii=False)
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
  <p class="subtitle">绝对计算法 · 表格计算法 · 列车到达站图</p>
</header>
<main>
{selector_card()}
<div id="resultRoot">
{body}
</div>
</main>
<footer>
  <p>© 2026 <a href="https://dickwxyz.github.io/resume" class="qa-link" target="_blank" rel="noopener">钱晨</a> 上海应用技术大学 · 保留所有权利</p>
</footer>
</div>
<script id="bz-data" type="application/json">{data_json}</script>
<script>{RUNTIME_JS}</script>
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
