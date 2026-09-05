"""scripts.engine — 给定"列划分 + 超列(暂合) + 股道"的确定性调度引擎。

调度规则（经例 4.3 三方案 / 4.4 / 4.6 的 S1..S5 轨迹逐车核对）：
  R1 初牵：home 道待编列整体。坐底 = 远端连续属于 home 超列的前缀；其余牵出(1 挂)。
  R1 溜放：自远端起把"同一目标超列"的连续车段合为一钩溜放；保留贴机尾段
            = 远端? 不，贴机端（最右）连续满足「属 home 超列 或 去向=全局最大」的车组。
  R2.. 拆分：对每个装了 ≥2 个原始列(去向尚未收敛) 的超列股道整列牵出，
            再把其中每辆车溜入其"最终宿主"（= 其原始列的相邻更低去向所在超列的股道）。
  R终  连挂：非空股道按"块内最大去向"从大到小整列牵出（先牵大块贴机），
            最后记一个转线钩；牵出线即编成 1..n。

引擎不承诺"最优"，只保证确定性；planner 用它对若干(调整方案, 暂合方案, 尾段策略)
打分选优，以对齐教材钩数 / 或取最小成本。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .model import Car, Group, Stats, expand_groups, tracks_text
from .simulator import Yard, SimulationError


class EngineResult:
    def __init__(self) -> None:
        self.hooks = []          # list[HookStep]
        self.terminal = None     # 终态 text
        self.ok = False
        self.err = ""
        self.stats = Stats()
        self.lead_sorted = False
        self.final_tracks = {}   # {track: station 串}


def _cars_of(groups: List[Group]) -> List[Car]:
    return expand_groups(groups)


def schedule(groups: List[Group],
             columns: List[List[Group]],          # 列（下落/调整后）
             super_cols: List[List[int]],         # 超列 = 列下标列表(0-based)
             super_tracks: List[str],
             home: str,
             depart: str,
             keep_tail_max_run: bool = True,
             max_rounds: int = 40) -> EngineResult:
    """运行调度，返回 EngineResult。不抛异常，失败置 ok=False + err。"""
    res = EngineResult()
    # ---- 编码 ----
    col_of_pos: Dict[int, int] = {}
    for ci, col in enumerate(columns):
        for g in col:
            col_of_pos[g.pos] = ci
    super_of_col: Dict[int, int] = {}
    for si, cols in enumerate(super_cols):
        for c in cols:
            super_of_col[c] = si
    pos_to_super: Dict[int, int] = {g.pos: super_of_col[col_of_pos[g.pos]] for g in groups}
    track_of_super = super_tracks

    def car_track(st: int) -> str:
        return track_of_super[pos_to_super[st]]

    first_pos = groups[0].pos
    home_super = pos_to_super[first_pos]
    if track_of_super[home_super] != home:
        res.err = f"home 道 {home} 不是 home 超列({home_super + 1})所在道 {track_of_super[home_super]}"
        return res

    max_st = max(g.station for g in groups)
    track_order = list(track_of_super)
    y = Yard(groups, home, track_order)
    total = y.total
    rnd = [0]

    def nxt() -> int:
        rnd[0] += 1
        return rnd[0]

    def gid_pos_of(car: Car) -> int:
        return car.gid

    try:
        # ================= R1 初牵（坐底 = 远端连续属 home 超列前缀） =================
        home_cars = y.state.tracks[home]
        keep = 0
        for c in home_cars:
            if pos_to_super[c.gid] == home_super:
                keep += 1
            else:
                break
        if keep >= len(home_cars):
            res.err = "待编车列全部属 home 超列"
            return res
        y.pull_part(home, keep, nxt())

        # ================= R1 溜放 =================
        lead = y.state.lead
        # 尾段（机前集结）：贴机端连续满足「属 home 超列 或 去向=max_st」。
        # 若 home 超列是 messy（多列），其近机车端保留的车会在拆分轮与整列一起重溜到最终宿主；
        # 若 home 超列是单列，这些车已处最终近端，直接保留至成列。
        tail = 0
        for c in reversed(lead):
            if pos_to_super[c.gid] == home_super or c.station == max_st:
                tail += 1
            else:
                break
        cut = len(lead) - tail
        i = 0
        while i < cut:
            tgt = car_track(lead[i].gid)
            j = i
            while j < cut and car_track(lead[j].gid) == tgt:
                j += 1
            # 同目标连续段（按辆数）合一钩
            n = j - i
            y.throw(tgt, n, rnd[0], f"溜放({tgt})")
            i = j

        # ================= R2 拆分（dirty 超列 -> 最终宿主） =================
        # 若超列只含 1 个原始列 → 内容天然有序，无需拆分。
        # 若含 ≥2 列 → 整列牵出，把各车溜入"最终宿主"。
        def col_is_messy(sup: int) -> bool:
            return len(super_cols[sup]) >= 2

        messy = [s for s in range(len(super_cols)) if col_is_messy(s)]
        # 最终宿主：对每个位于 messy 超列 sup 的列 c，宿主 = 满足"列 c0<c 且不在 sup"的最近 c0 所在超列
        # 若没有更低的列（c 已是全局最小），则保持原超列。
        # 缓存避免重复牵出
        done_messy = set()
        rr = 0
        while rr < max_rounds and any(
                s not in done_messy and len(y.state.tracks[track_of_super[s]]) > 0
                for s in messy):
            sup = None
            # 挑一个还有车的 messy 超列处理
            for s in messy:
                if s not in done_messy and len(y.state.tracks[track_of_super[s]]) > 0:
                    sup = s
                    break
            if sup is None:
                break
            tgt_track = track_of_super[sup]
            content = list(y.state.tracks[tgt_track])
            if len(content) == 0:
                done_messy.add(sup)
                continue
            n_pull = len(content)
            # 整列牵出
            y.pull_all(tgt_track, nxt(), f"拆分牵出({tgt_track})")
            # ---- 最终宿主预计算（对全局 messy 列一次性算好） ----
            final_super: Dict[int, int] = {}
            all_cols_in_messy = set()
            for s in messy:
                for c in super_cols[s]:
                    all_cols_in_messy.add(c)
            for c in range(len(columns)):
                if c not in all_cols_in_messy:
                    final_super[c] = super_of_col[c]       # 非 messy 列留在原超列
            for c in sorted(all_cols_in_messy):
                host = None
                for c0 in range(c - 1, -1, -1):
                    if super_of_col[c0] != super_of_col[c]:
                        host = super_of_col[c0]
                        break
                final_super[c] = host if host is not None else super_of_col[c]
            # ---- 重溜本次牵出（含 R1 机前保留的 home-messy 近机车端车）：把本超列的车
            #     溜入各自最终宿主；保留贴机端"去向=max_st"的纯尾段不再重溜。 ----
            # 先算：近机端连续 max_st 尾段长度
            _S = 0
            while _S < len(y.state.lead) and y.state.lead[-1 - _S].station == max_st:
                _S += 1
            # 需重溜的本超列车数 = 牵出线上的"非 max 尾段"区域内属于 sup 的车
            need = 0
            for cc in y.state.lead[:len(y.state.lead) - _S]:
                if pos_to_super[cc.gid] == sup:
                    need += 1

            def _host_of_gid(_gid: int) -> str:
                _c = col_of_pos[_gid]
                return track_of_super[final_super.get(_c, super_of_col[_c])]

            while need > 0:
                gid0 = y.state.lead[0].gid
                if pos_to_super[gid0] != sup:
                    res.err = "拆分轮遇到不属于本超列的前端车，调度失败"
                    return res
                ht = _host_of_gid(gid0)
                j = 0
                while j < need and pos_to_super[y.state.lead[j].gid] == sup \
                        and _host_of_gid(y.state.lead[j].gid) == ht:
                    j += 1
                y.throw(ht, j, nxt(), f"归块溜放({ht})")
                need -= j
            done_messy.add(sup)
            rr += 1
            if rr >= max_rounds:
                res.err = "拆分轮数超限"
                return res
        y.check()

        # ================= R终 连挂 =================
        # 非空股道按"块内去向区间"降序整列牵出（先牵站值更大、且区间更高的块贴机端）
        nonempty = [t for t in track_order if y.state.tracks[t]]
        order = sorted(nonempty,
                       key=lambda t: (-max(c.station for c in y.state.tracks[t]),
                                      -min(c.station for c in y.state.tracks[t])))
        for t in order:
            y.pull_all(t, nxt(), "连挂")
        # 转线
        y.transfer(depart, nxt())
        y.check()

        if not y.is_sorted():
            res.err = "最终未按去向递增（引擎规则未收敛）"
            return res

        # ---- 统计 ----
        for h in y.hooks:
            if h.kind == "挂":
                res.stats.hooks_pull += 1
            elif h.kind == "溜":
                res.stats.hooks_throw += 1
            elif h.kind == "转":
                res.stats.hooks_transfer += 1
        res.stats.cheng = res.stats.hooks_pull * 2 + res.stats.hooks_throw + res.stats.hooks_transfer
        res.hooks = y.hooks
        res.ok = True
        res.lead_sorted = True
        return res
    except SimulationError as e:
        res.err = str(e)
        return res
