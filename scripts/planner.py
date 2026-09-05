"""scripts.planner — 求解总装：解析输入 → 下落 → (可调检测) → 暂合候选枚举 → 股道分配 → 引擎逐方案调度 → 目标打分 → best。

列分组候选（对口理论优先）：
  * 第 1 列（列一）一般不与他列合并；
  * 先给"不暂合（每列一线）"；再给"单对非相邻列合并"（如 二·四 / 二·五 / 三·五）；
  * 股道不够时再允许更密的合并（每组 ≤3 列）；枚举后交给引擎跑，跑不通（未编成）即剔除。
"""

from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Optional, Tuple

from . import parser
from .model import Group, Stats, station_counts, total_cars, tracks_text
from .engine import schedule
from .xialuo import xialuo
from . import tiaozheng

_CN = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def super_label(super_cols: List[List[int]]) -> str:
    parts = []
    for group in super_cols:
        parts.append("·".join(_CN[c + 1] for c in group))
    return "、".join(parts)


def _col_of_first(columns, first_pos):
    for i, col in enumerate(columns):
        if any(g.pos == first_pos for g in col):
            return i
    return 0


def enumerate_supers(columns: List[List[int]], budget: int) -> List[List[List[int]]]:
    """枚举可用的列分组（含预算过滤）。列数 K；budget = 可用股道数（含 home）。"""
    K = len(columns)
    out: List[List[List[int]]] = []

    def try_partition(parts):
        # parts: list of sorted col lists
        if len(parts) > budget:
            return
        # 列一(0) 单独（对口理论①），除非 K==1
        for p in parts:
            if 0 in p and len(p) > 1:
                return
        # 去重
        key = tuple(tuple(p) for p in parts)
        for exist in out:
            if tuple(tuple(e) for e in exist) == key:
                return
        out.append(parts)

    # 1) 不暂合
    if K <= budget:
        try_partition([[i] for i in range(K)])

    # 2) 单对非相邻列合并（列一不参与）
    non_adj = [(i, j) for i in range(1, K) for j in range(i + 1, K) if j - i > 1]
    if K - 1 <= budget:
        for i, j in non_adj:
            parts = [[x] for x in range(K)]
            parts[j] = [i, j]
            parts[i] = []
            parts = [sorted(p) for p in parts if p]
            try_partition(parts)

    # 3) 预算更紧：按需把剩余列分组（含相邻）为尺寸 ≤3 的若干块，每组列数 ≥2 才合
    if budget < K:
        # 允许把 0 也合入(万不得已),但首选不含0
        import itertools as it
        # 递归：把列 1..K-1 切成若干连续块 <=2? 采用集合分割太贵；这里采用"连续块"简化
        # 生产可处理的子集：把 0..K-1 排列成分块(每块连续，长度<=3)
        def gen(lo, acc):
            if lo == K:
                try_partition([sorted(p) for p in acc])
                return
            for ln in (1, 2, 3):
                if lo + ln <= K:
                    blk = list(range(lo, lo + ln))
                    # 若块含0且len>1 → 违反列一单独，仅在必要时允许(跳过，稍后尝试其他)
                    gen(lo + ln, acc + [blk])
        gen(0, [])
    return out


def _assign_tracks(home: str, allowed: List[str]) -> Tuple[List[str], int]:
    """给 super 顺序分配股道，返回 (super_tracks, home_super_index 在调用方确定)."""
    return list(allowed), allowed.index(home) if home in allowed else 0


def solve(groups: List[Group], home: str,
          allowed_tracks: Optional[List[str]] = None,
          depart: str = "DF",
          weights: Optional[Dict[str, float]] = None,
          columns_override: Optional[List[List[Group]]] = None) -> dict:
    """主入口：返回可直接 JSON 的结果 dict（与 /api/solve 契约一致）。"""
    budget = len(allowed_tracks) if allowed_tracks else max(2, total_cars(groups))
    if allowed_tracks is None:
        # 兜底：不限定线路 → 用足够多的虚拟道
        allowed_tracks = _make_allowed(home, budget)

    raw_cols = xialuo(groups)                      # 原始下落表
    if columns_override is not None:
        columns, adjust_moves = columns_override, []
    else:
        columns, adjust_moves = tiaozheng.adjust_with_moves(groups)   # 邻组化调整
    first_pos = groups[0].pos
    home_col = _col_of_first(columns, first_pos)
    K = len(columns)

    # 预收集候选列分组，预算=可用道数（super 数 ≤ 可用道数）
    candidates = enumerate_supers(columns, budget)

    meta = {
        "parsed_seq": [g.to_dict() for g in groups],
        "total_cars": total_cars(groups),
        "max_station": max(g.station for g in groups),
        "group_totals": dict(sorted(station_counts(groups).items())),
        "home_track": home,
        "allowed_tracks": allowed_tracks,
        "depart_track": depart,
    }

    if adjust_moves:
        adj_note = (f"调整 {len(adjust_moves)} 处：把边界可调车组移入相邻列形成「邻组」"
                    f"（去向 v 与 v+1 相邻同线，溜放省钩；对应教材表 4.6 / 4.17 同构）。")
    else:
        adj_note = "无可调车组，本算例无需调整（与教材原始下落表一致）。"
    stages = {
        "xialuo": {
            "header": [g.to_dict() for g in groups],
            "cols": [[g.to_dict() for g in col] for col in raw_cols],
        },
        "tiaozheng": {
            "note": adj_note,
            "moves": adjust_moves,
            "cols_after": [[g.to_dict() for g in col] for col in columns],
        },
        "track_budget": {"limit": budget},
    }

    schemes = []
    for si, super_cols in enumerate(candidates):
        # home 超列 = 含 home_col 的组
        home_sup = None
        for idx, grp in enumerate(super_cols):
            if home_col in grp:
                home_sup = idx
                break
        if home_sup is None:
            continue
        # 分配物理股道：home 超列 → home；其余依次给 allowed 中的其他道
        others = [t for t in allowed_tracks if t != home]
        # 若 allowed 包含 home 之外的道不足，给足合成道（兜底）
        need = len(super_cols) - 1
        while len(others) < need:
            others.append(f"{len(others) + 1}线")
        super_tracks = [home] * len(super_cols)
        non_home = [i for i in range(len(super_cols)) if i != home_sup]
        for k, idx in enumerate(non_home):
            super_tracks[idx] = others[k]

        r = schedule(groups, columns, super_cols, super_tracks, home, depart)
        if not r.ok:
            continue
        stats = r.stats
        w = weights or {"pull": 4.0, "throw": 1.0, "transfer": 1.0}
        stats.weighted = (w["pull"] * stats.hooks_pull
                          + w["throw"] * stats.hooks_throw
                          + w["transfer"] * stats.hooks_transfer)
        stats.tracks_used = len(super_cols)
        hooks = [h.to_dict(super_tracks) for h in r.hooks]
        final_lead = r.hooks[-1].state.lead if r.hooks else []
        formation = [c.station for c in final_lead]
        schemes.append({
            "id": f"s{len(schemes)}",
            "label": super_label(super_cols),
            "supercols": [sorted(c) for c in super_cols],
            "track_alloc": [{"super": super_label([c]), "track": super_tracks[i]}
                            for i, c in enumerate(super_cols)],
            "stats": stats.to_dict(),
            "hooks": hooks,
            "final_formation": formation,
            "best": False,
        })

    # 目标打分：weighted 最小；并列再比 total_hooks、线数
    if schemes:
        def keyfn(s):
            st = s["stats"]
            return (st["weighted"], st["total_hooks"], st.get("tracks_used", 99))
        schemes.sort(key=keyfn)
        best_id = schemes[0]["id"]
        for s in schemes:
            s["best"] = (s["id"] == best_id)
        # 权重默认取 4/1/1；此处以加权最小者为最优
    return {
        "success": True,
        "meta": meta,
        "stages": stages,
        "schemes": schemes,
        "best_scheme_id": schemes[0]["id"] if schemes else None,
    }


def _make_allowed(home: str, budget: int) -> List[str]:
    out = [home]
    try:
        base = int(home)
    except ValueError:
        base = 10
    while len(out) < budget:
        base += 1
        out.append(str(base))
    return out


def parse_and_solve(seq: str, home: str, depart: str,
                    allowed_tracks: Optional[List[str]] = None,
                    track_budget: Optional[int] = None,
                    station_order: Optional[str] = None,
                    weights: Optional[Dict[str, float]] = None,
                    columns_override: Optional[List[List[Group]]] = None) -> dict:
    groups = parser.parse_seq(seq, station_order)
    if allowed_tracks is None and track_budget is not None:
        allowed_tracks = _make_allowed(home, track_budget)
    if allowed_tracks is None:
        allowed_tracks = _make_allowed(home, max(3, total_cars(groups)))
    return solve(groups, home, allowed_tracks=allowed_tracks, depart=depart,
                 weights=weights, columns_override=columns_override)
