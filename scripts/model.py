"""scripts.model — 数据模型。

堆序唯一约定（写进 CLAUDE.md）:
    **任意股道 / 牵出线的状态列表一律「机车远端(内/左) → 机车端(右)」，机车端恒在右。**
    待编车列书写序 = 该序：索引 0 = 最远/内（编成后去向最小端），末元素贴机车。
    最终编成 = 去向 1..n 顺序拼接，n 贴机车端。

引用的"去向编号 station"= 站顺号 1..n（n = 最近中间站，贴机车端）。
记号 k_m = 去向 k 的 m 辆车（一个车组，算法/下落/调车表的原子单元）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Group:
    """一个原子车组（去向 station、辆数 count、在待编车列中的位置 pos，1-based）。"""
    station: int
    count: int
    pos: int

    def to_dict(self) -> dict:
        return {"station": self.station, "count": self.count, "pos": self.pos}


@dataclass(frozen=True)
class Car:
    """一辆车（模拟用）。gid = 所属 Group.pos，用于颜色/归属。"""
    station: int
    gid: int

    def to_dict(self) -> dict:
        return {"station": self.station, "gid": self.gid}


def expand_groups(groups: List[Group]) -> List[Car]:
    """把一个车组序列展开为逐辆序列（保持顺序），原子不可再拆。"""
    cars: List[Car] = []
    for g in groups:
        cars.extend([Car(g.station, g.pos)] * g.count)
    return cars


def station_counts(groups: List[Group]) -> Dict[int, int]:
    """分去向合计辆数。"""
    out: Dict[int, int] = {}
    for g in groups:
        out[g.station] = out.get(g.station, 0) + g.count
    return out


def total_cars(groups: List[Group]) -> int:
    return sum(g.count for g in groups)


@dataclass
class YardState:
    """某一钩执行后的全场状态。tracks: 股道名 -> 车列（远->机车端）；lead: 牵出线/机带车列。"""
    tracks: Dict[str, List[Car]] = field(default_factory=dict)
    lead: List[Car] = field(default_factory=list)

    def snapshot(self) -> "YardState":
        return YardState(
            tracks={k: [Car(c.station, c.gid) for c in v] for k, v in self.tracks.items()},
            lead=[Car(c.station, c.gid) for c in self.lead],
        )

    def total(self) -> int:
        return sum(len(v) for v in self.tracks.values()) + len(self.lead)

    def to_dict(self, track_order: Optional[List[str]] = None) -> dict:
        keys = track_order if track_order is not None else list(self.tracks.keys())
        return {
            "tracks": {k: [c.to_dict() for c in self.tracks.get(k, [])] for k in keys},
            "lead": [c.to_dict() for c in self.lead],
        }


@dataclass
class HookStep:
    """一条钩记录 + 执行后状态快照（前端逐步图零推导）。"""
    seq: int
    code: str                 # "10+15" / "13-1" / "DF3-17"
    op: str                   # "+" | "-" | "转线"
    track: str                # 作业股道号（转线为出发道）
    qty: int
    kind: str                 # "挂" | "溜" | "转"
    round: int                # 第几牵出轮
    note: str
    cars: List[int] = field(default_factory=list)   # 本钩涉及的逐辆去向值（远->近）
    state: Optional[YardState] = None                # 执行后快照

    def to_dict(self, track_order: Optional[List[str]] = None) -> dict:
        return {
            "seq": self.seq,
            "code": self.code,
            "op": self.op,
            "track": self.track,
            "qty": self.qty,
            "kind": self.kind,
            "phase_round": self.round,
            "note": self.note,
            "cars": self.cars,
            "state": None if self.state is None else self.state.to_dict(track_order),
        }


@dataclass
class Stats:
    hooks_pull: int = 0       # 挂车钩（推送钩）
    hooks_throw: int = 0      # 溜放钩（摘车钩）
    hooks_transfer: int = 0   # 转线钩
    cheng: int = 0            # 调车程（挂=2、溜=1、转=1）
    weighted: float = 0.0     # 目标成本
    tracks_used: int = 0

    @property
    def total_hooks(self) -> int:
        """产品口径：三种钩之和。"""
        return self.hooks_pull + self.hooks_throw + self.hooks_transfer

    @property
    def textbook_total(self) -> int:
        """教材口径：不含转线钩。"""
        return self.hooks_pull + self.hooks_throw

    def to_dict(self) -> dict:
        return {
            "hooks_pull": self.hooks_pull,
            "hooks_throw": self.hooks_throw,
            "hooks_transfer": self.hooks_transfer,
            "total_hooks": self.total_hooks,
            "textbook_total": self.textbook_total,
            "cheng": self.cheng,
            "weighted": round(self.weighted, 3),
            "tracks_used": self.tracks_used,
        }


def tracks_text(state: YardState) -> str:
    """调试用：输出各股道与牵出线内容（compact 打印）。"""
    parts = []
    for k in sorted(state.tracks.keys()):
        cars = state.tracks[k]
        parts.append(f"{k}:{' '.join(str(c.station) for c in cars) or '-'}")
    parts.append(f"LEAD:{' '.join(str(c.station) for c in state.lead) or '-'}")
    return " | ".join(parts)
