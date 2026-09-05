"""scripts.simulator — 调车作业的物理模拟器（钩计划生成核心）。

模型与约定（全局唯一，见 CLAUDE.md）：
  * 任一状态：股道 / 牵出线的车辆列表一律「机车远端(内/左) → 机车端(右)」，机车端恒在右；
    即索引 0 = 最远/内，末元素贴机车。
  * 机车在右侧作业。初始待编车列停在 home 股道，书写序 = 该序（索引 0 = 最远）。
  * 原语：
      pull(home, k)    第 1 钩：把 home 道远端前缀（属"坐底"列）留下，其余 k 辆牵出
      pull_all(track)  整列股道牵出（机车把该股道全部车辆挂到牵出线远端之前）
      throw(track, n)  自牵出线远端连续摘 n 辆，溜放至该股道外方（near 端）
      transfer(...)    转线钩（编成后转往出发场）

  挂车钩 lead = pulled + lead；摘车钩 track += lead[:n]; lead = lead[n:]。

本模块只提供"原语 + 记录逐钩快照"的低层；编成流程（轮计划 / 选择点）在 planner.py。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from .model import Car, HookStep, YardState, expand_groups, tracks_text
from . import model


class SimulationError(RuntimeError):
    pass


class Yard:
    """一个可执行的原语模拟器，记录每钩后的状态快照。"""

    def __init__(self, groups, home: str, track_order: List[str]):
        self.groups = list(groups)
        self.home = home
        self.track_order = list(track_order)     # 展示/渲染用的股道顺序
        self.state = YardState(
            tracks={t: [] for t in track_order},
            lead=[],
        )
        self.state.tracks[home] = expand_groups(self.groups)   # 初始整车列在 home
        self.hooks: List[HookStep] = []
        self.total = sum(g.count for g in self.groups)

    # ---- 原语 ----
    def _snap(self) -> YardState:
        return self.state.snapshot()

    def record(self, code: str, op: str, track: str, qty: int, kind: str,
               rnd: int, note: str, cars: List[int]) -> None:
        st = self._snap()
        h = HookStep(seq=len(self.hooks) + 1, code=code, op=op, track=track,
                     qty=qty, kind=kind, round=rnd, note=note, cars=cars,
                     state=st)
        self.hooks.append(h)

    def pull_part(self, track: str, keep_from_far: int, rnd: int, note: str = "") -> None:
        """把股道远端 keep_from_far 辆留下（坐底），其余全部牵出。"""
        cars = self.state.tracks[track]
        if keep_from_far < 0 or keep_from_far > len(cars):
            raise SimulationError("pull_part keep 越界")
        pulled = cars[keep_from_far:]
        kept = cars[:keep_from_far]
        self.state.tracks[track] = kept
        qty = len(pulled)
        self.state.lead = pulled + self.state.lead
        self.record(f"{track}+{qty}", "+", track, qty, "挂", rnd,
                    note or f"牵出（坐底 {keep_from_far} 辆）", [c.station for c in pulled])

    def pull_all(self, track: str, rnd: int, note: str = "") -> None:
        cars = self.state.tracks[track]
        qty = len(cars)
        self.state.tracks[track] = []
        self.state.lead = cars + self.state.lead
        self.record(f"{track}+{qty}", "+", track, qty, "挂", rnd,
                    note or "整列牵出", [c.station for c in cars])

    def throw(self, track: str, n: int, rnd: int, note: str = "") -> None:
        if n <= 0 or n > len(self.state.lead):
            raise SimulationError(f"throw {track} {n} 越界（lead={len(self.state.lead)}）")
        cut = self.state.lead[:n]
        self.state.lead = self.state.lead[n:]
        self.state.tracks[track] = self.state.tracks[track] + cut
        self.record(f"{track}-{n}", "-", track, n, "溜", rnd,
                    note or f"向{track}溜放", [c.station for c in cut])

    def transfer(self, depart: str, rnd: int, note: str = "转线至出发场") -> None:
        n = len(self.state.lead)
        self.record(f"{depart}-{n}", "转线", depart, n, "转", rnd, note,
                    [c.station for c in self.state.lead])
        # 语义上转线后车列离场；为便于渲染"编成"状态，此处保留 lead 作为编成车列快照，
        # 车辆数守恒不变量仍成立。转线钩不入 lead 长度统计的"摘"。

    # ---- 不变量 ----
    def check(self) -> None:
        if self.state.total() != self.total:
            raise SimulationError(
                f"车辆数不守恒：{self.state.total()} != {self.total}\n{tracks_text(self.state)}")

    def is_sorted(self) -> bool:
        st = [c.station for c in self.state.lead]
        return all(st[i] <= st[i + 1] for i in range(len(st) - 1))


def replay(groups, home: str, track_order: List[str],
           ops: List[Tuple[str, object]]) -> Optional[Yard]:
    """按 (方法名, 参数) 序列重放（供测试自洽）。"""
    y = Yard(groups, home, track_order)
    try:
        for name, args in ops:
            getattr(y, name)(*args)
            y.check()
    except SimulationError as e:
        raise e
    return y
