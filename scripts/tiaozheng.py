"""scripts.tiaozheng — 调整（可调车组 -> 邻组）。

教材：下落之后，"可调车组"可在两相邻列间移动；移动得当可与相邻车组形成
**邻组**（去向 v 与 v+1 相邻、同线连续），溜放时可一钩溜出，省 1 个溜放钩。

本模块实现确定性规则（已对表4.6 / 表4.17 / 表4.9(=不调整) 逐一核对）：

对列 k，若其**首**或**末**车组 g（去向 v）满足全部条件，则移入列 k+1：
  1. g 在待编序列中的直接右邻车组 h（下一车组）去向 == v+1，且 h **当前属于列 k+1**
     （即下落把本可成组的 v…v+1 拆到了相邻两列 —— 正是"可调/邻组"判据）；
  2. 列 k 移出后仍非空（保留 ≥1 车组）；列 k+1 按位置插入 g 后仍去向非降；
  3. 保护坐底结构：若 g 属于"含待编首车组(pos1)的列"的**远端连续前缀**（pos1 起连续同列），
     则不移（否则会破坏 home 列 / 坐底，如例4.3 的 5₂@pos1、例4.6 的 4₂5₂ 被教材保留）。

只向右移（列 k → 列 k+1）；列数 K 不变，每列保持非空。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .model import Group
from .xialuo import xialuo


def _nondec(lst: List[Group]) -> bool:
    return all(lst[i].station <= lst[i + 1].station for i in range(len(lst) - 1))


def adjust_with_moves(groups: List[Group]) -> Tuple[List[List[Group]], List[dict]]:
    """下落 → 邻组化调整。

    返回 (调整后列, moves)。moves 元素：
        {pos, station, count, from_col, to_col, neighbor_pos}  （列号从 0 起）
    """
    cols: List[List[Group]] = [list(c) for c in xialuo(groups)]
    K = len(cols)
    if K <= 1:
        return cols, []

    by_pos: Dict[int, Group] = {g.pos: g for g in groups}

    def col_containing(pos: int) -> Optional[int]:
        for i, col in enumerate(cols):
            if any(g.pos == pos for g in col):
                return i
        return None

    # home 列 = 含 pos1 的列；远端连续前缀 = pos1 起连续同列的车组位置（坐底前缀）
    home_col = col_containing(1)
    prefix_pos = set()
    for g in groups:                        # groups 按 pos 升序
        if col_containing(g.pos) == home_col:
            prefix_pos.add(g.pos)
        else:
            break

    moves: List[dict] = []

    def boundary_of(col: List[Group]) -> List[Group]:
        out = []
        if col and col[0].pos not in prefix_pos:
            out.append(col[0])
        if len(col) > 1 and col[-1].pos not in prefix_pos:
            if col[-1].pos != (col[0].pos if col else None):
                out.append(col[-1])
        return out

    changed = True
    guard = 0
    while changed and guard < 200:
        changed = False
        guard += 1
        for k in range(K - 1):
            moved_here = True
            while moved_here:
                moved_here = False
                if len(cols[k]) <= 1:
                    break
                for g in boundary_of(cols[k]):
                    v = g.station
                    h = by_pos.get(g.pos + 1)
                    if h is None or h.station != v + 1:
                        continue
                    if col_containing(h.pos) != k + 1:
                        continue
                    new_next = sorted(cols[k + 1] + [g], key=lambda x: x.pos)
                    if not _nondec(new_next):
                        continue
                    cols[k].remove(g)
                    cols[k + 1] = new_next
                    moves.append({
                        "pos": g.pos, "station": g.station, "count": g.count,
                        "from_col": k, "to_col": k + 1, "neighbor_pos": h.pos,
                    })
                    changed = True
                    moved_here = True
                    break
    return cols, moves


def adjust(groups: List[Group]) -> List[List[Group]]:
    cols, _ = adjust_with_moves(groups)
    return cols
