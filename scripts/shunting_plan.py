"""scripts.shunting_plan — 门面（兼容 app.py 的 import 路径）。

用法：
    ShuntingPlan(seq=..., home_track=..., allowed_tracks=...|track_budget=...,
                 depart_track=..., station_order=..., weights=...).solve()
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .planner import parse_and_solve


class ShuntingPlan:
    def __init__(self, seq: str,
                 home_track: str = "10",
                 allowed_tracks: Optional[List[str]] = None,
                 track_budget: Optional[int] = None,
                 depart_track: str = "DF",
                 station_order: Optional[str] = None,
                 weights: Optional[Dict[str, float]] = None):
        self.seq = seq
        self.home_track = home_track
        self.allowed_tracks = allowed_tracks
        self.track_budget = track_budget
        self.depart_track = depart_track
        self.station_order = station_order
        self.weights = weights

    def solve(self) -> dict:
        return parse_and_solve(
            self.seq, self.home_track, self.depart_track,
            allowed_tracks=self.allowed_tracks,
            track_budget=self.track_budget,
            station_order=self.station_order,
            weights=self.weights)
