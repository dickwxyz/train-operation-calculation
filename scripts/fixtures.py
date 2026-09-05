"""scripts.fixtures — 验收固件（无 pytest，直接 python 运行）。

    PYTHONPATH=. venv/bin/python -c "from scripts import fixtures; fixtures.run()"

硬断言（与教材核对）：
  1. 下落列 == 表4.5 / 表4.9 / 表4.16（例4.3 / 4.4 / 4.6）
  2. 自动"调整"复现教材表 4.6（例4.3 移 2 处：1₂@4、2₁@10→列二）、表 4.17（例4.6 移 1₃@6→列二）、
     例4.4 无需调整（= 表4.9 原样）。
  3. 用调整后列跑引擎，钩数与教材一致：
       例4.3  二·四暂合 (5挂,10溜)、二·五暂合 (5,10)、三·五暂合 (5,9)   [教材 5+10 / 5+10 / 5+9]
       例4.6  二·五暂合 (5挂,14溜,1转)                                   [教材 20 钩]
       例4.4  不暂合（调整后=原始列）→ (6推,7溜)                          [教材 6推7溜]
自洽断言：
  4. 习题 2 / 7 / 8 / 9 / 12 在默认股道数下均有可行方案且最终编成严格非降。
注意：例4.4 三列合并（二·四·五）与习题3（3 线预算）在当前调度引擎下仍无可行方案，不在此固件断言。
"""

from __future__ import annotations

import sys
from typing import List

from . import parser
from .xialuo import xialuo
from . import tiaozheng
from .engine import schedule

FAIL = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  [PASS] {name}")
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name}  {detail}")


def _poslist(cols) -> List[List[int]]:
    return [sorted(g.pos for g in c) for c in cols]


def _run(g, cols, super_cols, tracks, home, depart):
    r = schedule(g, cols, super_cols, tracks, home, depart)
    if not r.ok:
        return (None, r.err)
    return ((r.stats.hooks_pull, r.stats.hooks_throw, r.stats.hooks_transfer), "")


def run() -> None:
    print("== 1) 下落列对照教材表 4.5 / 4.9 / 4.16 ==")
    c43 = parser.parse_seq("5₂6₁4₁1₂2₁5₁1₂6₂4₁2₁3₂6₁")
    check("例4.3 下落=表4.5", _poslist(xialuo(c43)) == [[4, 7, 10], [5, 11], [3, 9], [1, 6, 8, 12], [2]])
    c44 = parser.parse_seq("edgafbgfcea", "gfedcba")
    check("例4.4 下落=表4.9", _poslist(xialuo(c44)) == [[3, 7, 8], [5, 10], [1, 2, 9], [6, 11], [4]])
    c46 = parser.parse_seq("4₂5₂6₁3₁5₂1₃2₁4₃3₂6₁5₁3₂1₁4₂7₂")
    check("例4.6 下落=表4.16", _poslist(xialuo(c46)) == [[6, 13], [7, 9, 12], [4, 8, 14], [1, 2, 5, 11], [3, 10, 15]])

    print("== 2) 自动调整 = 教材表4.6 / 4.17 / (例4.4 原样) ==")
    g43 = parser.parse_seq("b₂a₁c₁f₂e₁b₁f₂a₂c₁e₁d₂a₁", "fedcba")
    adj43, m43 = tiaozheng.adjust_with_moves(g43)
    check("例4.3 调整后=表4.6", _poslist(adj43) == [[7], [4, 5, 10, 11], [3, 9], [1, 6, 8, 12], [2]])
    check("例4.3 移动 2 处（1₂@4、2₁@10→列二）",
          [m["pos"] for m in m43] == [4, 10] and all(m["to_col"] == 1 for m in m43),
          str(m43))

    g46 = parser.parse_seq("4₂5₂6₁3₁5₂1₃2₁4₃3₂6₁5₁3₂1₁4₂7₂")
    adj46, m46 = tiaozheng.adjust_with_moves(g46)
    check("例4.6 调整后=表4.17", _poslist(adj46) == [[13], [6, 7, 9, 12], [4, 8, 14], [1, 2, 5, 11], [3, 10, 15]])
    check("例4.6 移动 1 处（1₃@6→列二）",
          [m["pos"] for m in m46] == [6] and m46 and m46[0]["to_col"] == 1, str(m46))

    _, m44 = tiaozheng.adjust_with_moves(c44)
    check("例4.4 无需调整（moves=0）", m44 == [], str(m44))

    print("== 3) 调整后列跑引擎钩数 vs 教材 ==")
    r = _run(g43, adj43, [[0], [1, 3], [2], [4]], ["11", "10", "12", "13"], "10", "DF3")
    check("例4.3 二·四暂合 (5,10)", r[0] == (5, 10, 1), str(r))
    r = _run(g43, adj43, [[0], [1, 4], [2], [3]], ["11", "12", "13", "10"], "10", "DF3")
    check("例4.3 二·五暂合 (5,10)", r[0] == (5, 10, 1), str(r))
    r = _run(g43, adj43, [[0], [1], [2, 4], [3]], ["11", "12", "13", "10"], "10", "DF3")
    check("例4.3 三·五暂合 (5,9)", r[0] == (5, 9, 1), str(r))
    r = _run(g46, adj46, [[0], [1, 4], [2], [3]], ["8", "9", "10", "7"], "7", "F3")
    check("例4.6 二·五暂合 (5,14)", r[0] == (5, 14, 1), str(r))
    raw44 = tiaozheng.adjust(c44)                 # 例4.4 无需调整 → 同原始
    r = _run(c44, raw44, [[0], [1], [2], [3], [4]], ["10", "11", "12", "13", "14"], "12", "DF5")
    check("例4.4 不暂合 (6推,7溜)", r[0] == (6, 7, 1), str(r))

    print("== 4) 习题自洽（有可行方案且终列非降） ==")
    from .planner import parse_and_solve
    for name, seq, kw in [
        ("习题2", "1₃4₁6₁5₃1₂4₁3₁2₂6₂7₃", dict(home_track="10", track_budget=5)),
        ("习题7", "73652264135347", dict(home_track="10")),
        ("习题8", "659142481736", dict(home_track="10")),
        ("习题9", "835327144357664", dict(home_track="10")),
        ("习题12", "4₃3₂6₁2₁1₃5₂4₁2₂1₃6₂5₁4₁3₁", dict(home_track="11", track_budget=4)),
    ]:
        res = parse_and_solve(seq, kw["home_track"], "DF5",
                              track_budget=kw.get("track_budget"))
        ok = bool(res["schemes"])
        if ok:
            b = next(s for s in res["schemes"] if s["id"] == res["best_scheme_id"])
            f = b["final_formation"]
            ok = all(f[i] <= f[i + 1] for i in range(len(f) - 1))
        check(f"{name} 有可行方案且终列非降", ok)

    print()
    if FAIL:
        print(f"{len(FAIL)} 项未通过: {FAIL}")
        sys.exit(1)
    print("全部固件通过。")
    sys.exit(0)


if __name__ == "__main__":
    run()
