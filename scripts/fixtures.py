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
  5. 例题白名单闸门（scripts.mode）：**锁定态下**（显式 locked=True，与当前出厂 MODE 无关）
     只放行 3 个例题；规范形对"站号重命名 / 车组改写 / 书写格式"均不变，故 6 个习题的原题与
     各种变形一律被拒（含用户实测报出的「原题+站序7654321」「展开式」两条绕过）；
     前端 index.html 的习题 PRESETS 不在白名单；mode_payload 与 MODE 自洽。
注意：例4.4 三列合并（二·四·五）与习题3（3 线预算）在当前调度引擎下仍无暂合可行方案；
习题3 只显示不合并基准方案，基准断言见 4b。
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

    print("== 4b) 基准方案（不合并下落列，按股道充足假设生成） ==")
    for name, p in parser.PRESETS.items():
        res = parse_and_solve(p["seq"], p["home_track"], p["depart_track"],
                              allowed_tracks=p.get("allowed_tracks"),
                              track_budget=p.get("track_budget"),
                              station_order=p.get("station_order"))
        sch = res["schemes"]
        base = sch[0] if sch else None
        ok = bool(base and base.get("baseline"))
        if ok:
            f = base["final_formation"]
            ok = all(f[i] <= f[i + 1] for i in range(len(f) - 1))
        if ok:
            # 基准只作比较参照：任何题目的基准都不带 ★
            ok = not any(s.get("best") and s.get("baseline") for s in sch)
        check(f"{name} 有基准方案（排第一、终列非降、不评最优）", ok,
              str([(s["label"], s.get("baseline"), s["best"]) for s in sch]))

    res = parse_and_solve("b₂a₁c₁f₂e₁b₁f₂a₂c₁e₁d₂a₁", "10", "DF3",
                          allowed_tracks=["10", "11", "12", "13"], station_order="fedcba")
    b = res["schemes"][0]
    check("例4.3 基准股道=教材表4.7",
          {a["track"] for a in b["track_alloc"]} == {"10", "11", "12", "13", "14"},
          str(b["track_alloc"]))
    check("例4.3 基准 6挂8溜",
          (b["stats"]["hooks_pull"], b["stats"]["hooks_throw"]) == (6, 8), str(b["stats"]))

    res = parse_and_solve("3₁4₂7₃6₂1₃2₁5₃1₁3₂5₃3₁", "10", "DF5", track_budget=3)
    check("习题3 仅显示基准方案且无最优",
          len(res["schemes"]) == 1 and res["schemes"][0].get("baseline")
          and res["best_scheme_id"] is None and bool(res.get("note")),
          str([(s["label"], s.get("baseline")) for s in res["schemes"]]))

    print("== 4c) 三列暂合（二·四·五，deep_merge） ==")
    TRIPLE = [[0], [1, 3, 4], [2]]
    r44 = parse_and_solve("edgafbgfcea", "12", "DF5",
                          allowed_tracks=["10", "11", "12", "13", "14"],
                          station_order="gfedcba", deep_merge=True)
    t44 = next((s for s in r44["schemes"] if s["supercols"] == TRIPLE), None)
    check("例4.4 三列暂合存在且最优", bool(t44 and t44["best"]),
          str([(s["label"], s["best"]) for s in r44["schemes"]]))
    if t44:
        st = t44["stats"]
        check("例4.4 三列暂合 5挂7溜（教材方案一）",
              (st["hooks_pull"], st["hooks_throw"], st["hooks_transfer"]) == (5, 7, 1),
              str(st))
        f = t44["final_formation"]
        check("例4.4 三列暂合终列非降",
              all(f[i] <= f[i + 1] for i in range(len(f) - 1)), str(f))
        check("例4.4 三列暂合钩序=算例集方案一",
              [h["code"] for h in t44["hooks"]] ==
              ["12+9", "10-1", "11-3", "10-2", "12-1", "11+2", "10-1",
               "12-1", "10-1", "11+1", "12+4", "10+5", "DF5-11"],
              str([h["code"] for h in t44["hooks"]]))

    r3d = parse_and_solve("3₁4₂7₃6₂1₃2₁5₃1₁3₂5₃3₁", "10", "DF5",
                          track_budget=3, deep_merge=True)
    t3 = next((s for s in r3d["schemes"] if s["supercols"] == TRIPLE), None)
    if t3:
        st = t3["stats"]
        f = t3["final_formation"]
        check("习题3 三列暂合 5挂7溜且终列非降",
              (st["hooks_pull"], st["hooks_throw"], st["hooks_transfer"]) == (5, 7, 1)
              and all(f[i] <= f[i + 1] for i in range(len(f) - 1)), str(st))
        check("习题3 三列暂合为最优", t3["best"] and r3d["best_scheme_id"] == t3["id"],
              str(r3d["best_scheme_id"]))
    else:
        check("习题3 三列暂合存在", False, str([s["label"] for s in r3d["schemes"]]))

    r44d = parse_and_solve("edgafbgfcea", "12", "DF5",
                           allowed_tracks=["10", "11", "12", "13", "14"],
                           station_order="gfedcba")
    check("例4.4 默认（deep_merge=False）不枚举三列暂合",
          all(s["supercols"] != TRIPLE for s in r44d["schemes"]),
          str([s["label"] for s in r44d["schemes"]]))

    print("== 5) 例题白名单闸门（scripts.mode） ==")
    import pathlib
    import re
    from . import mode

    def _groups(name):
        p = parser.PRESETS[name]
        return parser.parse_seq(p["seq"], p.get("station_order") or None)

    def _variants(groups):
        """同一题在 parser 支持的各写法下的等价串（由已解析车组生成，杜绝手抄出错）。"""
        gs = list(groups)
        out = {
            "下标原样": parser.groups_to_text(gs),
            "下划线空格": " ".join(f"{g.station}_{g.count}" for g in gs),
            "下划线逗号": ",".join(f"{g.station}_{g.count}" for g in gs),
            "逐辆展开": " ".join(str(g.station) for g in gs for _ in range(g.count)),
        }
        if all(g.count == 1 for g in gs):
            out["纯数字串"] = "".join(str(g.station) for g in gs)
        return out

    def _relabel_digits(groups):
        """把逐辆去向整体重命名（s → max+1-s）后写成纯数字串。

        模拟学生"改站号 / 改站序"的变形 —— 规范形对此应当不变。
        """
        cars = [g.station for g in groups for _ in range(g.count)]
        top = max(cars)
        if top > 9:                     # 纯数字串在多位数下会歧义，跳过
            return None
        return "".join(str(top + 1 - s) for s in cars)

    check("MODE 与 LOCKED 自洽", mode.LOCKED == (mode.MODE == "locked"),
          f"MODE={mode.MODE}")
    # 本节以下断言一律**显式传 locked=True**，验证的是闸门机制本身，与当前出厂 MODE 无关：
    # 出厂 MODE="full" 时机制仍需完好，改回 "locked" 打包即生效。
    check("预设点名均存在", mode.MISSING_PRESETS == [], str(mode.MISSING_PRESETS))

    # 前端靠 /api/mode 决定习题按钮是否置灰：payload 必须与 MODE 一致
    # （改了 mode.py 忘了同步此处会暴露；MODE="full" 时前端才会解除置灰）
    payload = mode.mode_payload()
    check("mode_payload 与 MODE 一致",
          payload["mode"] == mode.MODE
          and payload["exercise_locked"] == mode.LOCKED
          and payload["example_only"] == mode.LOCKED,
          str(payload))

    print("  -- 规范形对「站号重命名 / 车组改写」不变 --")
    for name in mode.LOCKED_EXERCISES:
        g = _groups(name)
        base = mode.canonical(g)
        for label, text in _variants(g).items():
            check(f"{name} {label} 规范形不变",
                  mode.canonical(parser.parse_seq(text, None)) == base)
        rel = _relabel_digits(g)
        if rel:
            check(f"{name} 站号重命名 规范形不变",
                  mode.canonical(parser.parse_seq(rel)) == base)

    print("  -- 锁定态：例题放行 --")
    for name in mode.ALLOWED_EXAMPLES:
        g = _groups(name)
        check(f"{name} 原样放行", mode.is_allowed(g, locked=True))
        for label, text in _variants(g).items():
            check(f"{name} {label}放行",
                  mode.is_allowed(parser.parse_seq(text, None), locked=True))
        rel = _relabel_digits(g)
        if rel:
            check(f"{name} 站号重命名放行",
                  mode.is_allowed(parser.parse_seq(rel), locked=True))

    print("  -- 锁定态：习题一律拒绝（含全部变形）--")
    for name in mode.LOCKED_EXERCISES:
        g = _groups(name)
        check(f"{name} 原样拒绝", not mode.is_allowed(g, locked=True))
        for label, text in _variants(g).items():
            check(f"{name} {label}拒绝",
                  not mode.is_allowed(parser.parse_seq(text, None), locked=True))
        rel = _relabel_digits(g)
        if rel:
            check(f"{name} 站号重命名拒绝",
                  not mode.is_allowed(parser.parse_seq(rel), locked=True))

    # 用户实测报出的三条绕过，固化为回归
    check("回归：习题2 原题 + 站序7654321 被拒",
          not mode.is_allowed(parser.parse_seq("1₃4₁6₁5₃1₂4₁3₁2₂6₂7₃", "7654321"),
                              locked=True))
    check("回归：习题2 展开式被拒",
          not mode.is_allowed(parser.parse_seq("1114655511432266777"), locked=True))
    check("回归：习题2 展开式 + 站序7654321 被拒",
          not mode.is_allowed(parser.parse_seq("1114655511432266777", "7654321"),
                              locked=True))

    # 白名单的既定代价：学生自编数据也被拒（旧版这条是"放行"，已反转）
    check("学生自编数据被拒（白名单既定代价）",
          not mode.is_allowed(parser.parse_seq("4₂5₂6₁3₁5₂1₃2₁4₃3₂6₁5₁3₂1₁4₂7₁"),
                              locked=True))

    # 解锁态（MODE="full" / 教师演示版）放行一切
    check("解锁态（locked=False）放行一切",
          mode.is_allowed(_groups("习题2"), locked=False)
          and mode.is_allowed(parser.parse_seq("4₂5₂6₁3₁5₂1₃2₁4₃3₂6₁5₁3₂1₁4₂7₁"),
                              locked=False))

    # 结构自洽：6 个习题规范形互不相同，且不与任何例题撞车
    ex_keys = [mode.canonical(_groups(n)) for n in mode.LOCKED_EXERCISES]
    check("6 个习题规范形互不相同", len(set(ex_keys)) == len(ex_keys))
    check("习题规范形不与任何例题撞车",
          not (set(ex_keys) & {mode.canonical(_groups(n)) for n in mode.ALLOWED_EXAMPLES}))

    # 前端 PRESETS 防漂移：index.html 里习题按钮会填进去的那串，必须不在白名单
    # （锁定态下判定 —— 保证改回 MODE="locked" 时白名单没被悄悄塞进习题）
    html = (pathlib.Path(__file__).resolve().parent.parent
            / "static" / "index.html").read_text(encoding="utf-8")
    found = re.findall(
        r'"(习题\d+)":\s*\{\s*seq:\s*"([^"]+)",\s*station_order:\s*"([^"]*)"', html)
    check("前端 PRESETS 抓取到 6 个习题（正则失效会在此暴露）", len(found) == 6,
          f"抓到 {len(found)} 条")
    for nm, seq, so in found:
        check(f"前端 {nm} 不在白名单（防前后端漂移）",
              not mode.is_allowed(parser.parse_seq(seq, so or None), locked=True))

    print()
    if FAIL:
        print(f"{len(FAIL)} 项未通过: {FAIL}")
        sys.exit(1)
    print("全部固件通过。")
    sys.exit(0)


if __name__ == "__main__":
    run()
