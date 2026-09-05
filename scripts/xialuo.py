"""scripts.xialuo — 调车表法第一步：车组下落。

下落把待编车列中"反顺序"的车组分解到不同"下落列"（一列将占一条线路/或并入暂合列）。
每列内部去向值非降，且同一列车组按在待编车列中的位置（pos）自左至右。

逐列基准（教材规则）：
  第 1 列基准 = 全部去向的最小值；
  第 k 列基准 = 第 k-1 列最后落下车组的去向值（该去向已无剩余则顺延到下一个在列的较大去向）。

单列填写规则：
  以当前值 v 开始：落下剩余中全部去向 = v 的车组（自左至右），记其最右位置 R；
  然后考察 v+1：
    * 若剩余中存在去向 v+1 且其位置在 R 之左（反顺序）→ 只落 R 之右的 v+1 车组，本列结束；
    * 否则（全部在 R 之右或没有）→ 落下全部 v+1 车组，令 v = v+1 继续；
  中间某值无剩余时跳过。列内各车组位置严格递增 → 物理上即按到达次序落位。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .model import Group


def _one_column(stations: List[int], remaining: List[int], base: int) -> List[int]:
    """返回本列落下车组的下标（0-based，自左至右），并从 remaining 移除。"""
    col: List[int] = []
    R: Optional[int] = None            # 本列已落车组的最右位置
    v = base
    present = {stations[p] for p in remaining}
    max_v = max(stations) if stations else 0

    while True:
        # 顺延 v 到"剩余中存在的去向"
        while v <= max_v and v not in present:
            v += 1
        if v > max_v or not remaining:
            break
        vals = [p for p in remaining if stations[p] == v]   # remaining 已按位置升序
        if R is not None and any(p < R for p in vals):
            # 反顺序：只能落 R 之右的 v 车组，然后本列结束
            placed = [p for p in vals if p > R]
            if placed:
                for p in placed:
                    remaining.remove(p)
                col.extend(placed)
            break
        # 无反顺序：落下全部 v 车组
        for p in vals:
            remaining.remove(p)
        col.extend(vals)
        if vals:
            R = max(vals) if R is None else max(R, max(vals))
        if not remaining:
            break
        present = {stations[p] for p in remaining}
        v = v + 1
    return col


def xialuo(groups: List[Group]) -> List[List[Group]]:
    """下落主流程 → 列列表 cols[0..k]，每列是 Group 列表（位置升序、去向非降）。"""
    stations = [g.station for g in groups]
    n = len(groups)
    remaining = list(range(n))          # 保持升序
    cols_idx: List[List[int]] = []
    # 第 1 列基准 = 最小去向
    base = min(stations)
    while remaining:
        col = _one_column(stations, remaining, base)
        if not col:                      # 理论上不会发生；保险退出
            break
        cols_idx.append(col)
        # 下一列基准 = 上一列最后落下车组的去向值（顺延逻辑在 _one_column 内做）
        base = stations[col[-1]]
    cols: List[List[Group]] = []
    for col in cols_idx:
        cols.append([groups[i] for i in sorted(col)])
    return cols


def col_of_group(groups: List[Group], cols: List[List[Group]]) -> Dict[int, int]:
    """group.pos -> 列号（1-based），供前端调车表与后续暂合使用。"""
    out: Dict[int, int] = {}
    for c, col in enumerate(cols, start=1):
        for g in col:
            out[g.pos] = c
    return out


def render_header(groups: List[Group]) -> List[dict]:
    """调车表表头：每个车组格（含去向值、辆数、位置）。"""
    return [g.to_dict() for g in groups]
