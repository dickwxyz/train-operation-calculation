"""scripts.mode — 运行模式与「例题白名单」闸门。

模式在**开发时定死**：改下面的 MODE 常量后重新打包上传（学生端无法更改）。

锁定版**只放行 3 个例题**，其余输入一律拒绝 —— 学生拿习题原题、各种变形、
或自编数据都换不到答案。之所以用白名单而不是"习题黑名单"：黑名单要追着学生的
变形跑，而输入至少有三种自由度（站号重命名、车组改写、书写格式），实测能绕过；
白名单只需认死例题。

闸门只装在 **HTTP 边界**（`app.py` 的 `/api/solve`），库层 `planner` / `ShuntingPlan`
刻意不设闸 —— 教师本地验算、`fixtures` 回归照常跑，不会被自己挡住。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from . import parser as _parser

# =========================================================================
# ↓↓↓ 唯一开关：打包给学生必须保持 "locked" ↓↓↓
# =========================================================================
MODE: str = "locked"        # "locked" = 教学版（只放行例题）| "full" = 完整版
LOCKED: bool = (MODE == "locked")

#: 锁定版放行的算例
ALLOWED_EXAMPLES: Tuple[str, ...] = ("例4.3", "例4.4", "例4.6")

#: 课后习题（不进白名单）。此处仅用于**区分提示文案**，不参与放行判定。
LOCKED_EXERCISES: Tuple[str, ...] = (
    "习题2", "习题3", "习题7", "习题8", "习题9", "习题12",
)

EXERCISE_MESSAGE = (
    "该车列是课后习题的原始数据，已锁定，暂不提供求解结果。"
    "请先独立完成（下落 → 调整 → 暂合 → 钩计划），再向教师索取答案。"
)
EXAMPLE_ONLY_MESSAGE = (
    "教学版仅开放 3 个例题（例4.3 / 例4.4 / 例4.6），其它车列（含自编数据）不提供求解。"
    "如确需演示其它算例，请使用完整版。"
)


def canonical(groups) -> Tuple[int, ...]:
    """规范形：逐辆去向 → 首次出现次序（1 起）。

    对下列改写**均不变**，因此靠变形绕不开：
      * **站号重命名** —— 任意 `station_order`、任意一一映射（如 `7654321`）；
      * **车组边界改写** —— `1₃` 与 `1 1 1` 同形；
      * **书写格式** —— 下标 / `4_2` / 空格 / 逗号（`parse_seq` 已先归一）。

    注意是**逐辆**展开：车组边界被刻意忽略，否则"展开写法"就是一条绕过路径。
    """
    rank: Dict[int, int] = {}
    out: List[int] = []
    for g in groups:
        for _ in range(g.count):
            r = rank.get(g.station)
            if r is None:
                r = len(rank) + 1
                rank[g.station] = r
            out.append(r)
    return tuple(out)


def _canon_of_preset(name: str) -> Tuple[int, ...]:
    preset = _parser.PRESETS[name]
    return canonical(_parser.parse_seq(preset["seq"], preset.get("station_order") or None))


def _build_keys(names: Tuple[str, ...]) -> Tuple[set, List[str]]:
    keys, missing = set(), []
    for name in names:
        if name not in _parser.PRESETS:
            missing.append(name)
            continue
        keys.add(_canon_of_preset(name))
    return keys, missing


#: 例题规范形（放行集）；#: 习题规范形（仅用于提示文案）
ALLOWED_KEYS, _MISSING_EXAMPLES = _build_keys(ALLOWED_EXAMPLES)
EXERCISE_KEYS, _MISSING_EXERCISES = _build_keys(LOCKED_EXERCISES)
#: 点名却找不到的预设（应为空，由 fixtures 断言暴露）
MISSING_PRESETS: List[str] = _MISSING_EXAMPLES + _MISSING_EXERCISES


def is_exercise(groups) -> bool:
    """是否命中某个课后习题的规范形（用于提示文案）。"""
    return canonical(groups) in EXERCISE_KEYS


def is_allowed(groups, locked: bool = None) -> bool:
    """锁定版放行判定：只有规范形命中例题才放行。

    ``locked`` 缺省取模块常量；测试可显式传 ``False`` 验证解锁态。
    """
    if not (LOCKED if locked is None else locked):
        return True
    return canonical(groups) in ALLOWED_KEYS


def reject_message(groups) -> str:
    """拒绝时给学生的提示：命中习题与其它输入分开说。"""
    return EXERCISE_MESSAGE if is_exercise(groups) else EXAMPLE_ONLY_MESSAGE


def mode_payload() -> Dict:
    """给前端的模式信息（前端据此置灰习题按钮、显示"仅开放例题"提示）。"""
    return {
        "mode": MODE,
        "exercise_locked": LOCKED,
        "example_only": LOCKED,
        "allowed_examples": list(ALLOWED_EXAMPLES),
        "locked_names": list(LOCKED_EXERCISES),
    }
