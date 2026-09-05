"""scripts.parser — 宽容解析待编车列序列。

支持写法（可混用空格 / 逗号分隔）：
  * 带下标   "4₂ 5₂ 6₁ 3₁ 5₂ 1₃ …"       下标 ₁..₉ 表示该车组辆数
  * 下划线   "4_2 5_2 6_1"                  k_n 形式
  * 纯数字串 "73652264135347"               每字符 = 去向编号 1 辆
  * 字母串   "edgafbgfcea"                  每字符 = 一个站名（1 辆），须给 station_order
  * 混合     "3 4 1 7 2 6 1 2 5 3 7"

station_order（可选）：编成顺序字符串，自最远到最近，如例4.3 编成 fedcba → "fedcba"，
此时 f→1, e→2, …, a→6。缺省且为数字时去向编号即站顺号（须连续 1..n）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .model import Group

# 下标字符 -> 数字（U+2080..U+2089）
_SUBSCRIPTS: Dict[str, int] = {chr(0x2080 + i): i for i in range(10)}
_SUB_SET = set(_SUBSCRIPTS)


class ParseError(ValueError):
    pass


def _strip_subs(c: str) -> Optional[int]:
    return _SUBSCRIPTS.get(c)


def tokenize_attached_subscripts(text: str) -> List[Tuple[str, int]]:
    """解析无分隔符、但带下标字符的串，如 "4₂5₂6₁3₁…" 或 "b₂a₁c₁…"。

    返回 [(raw_station, count)]。单个站名假定为 1 个字符（本教材习题站号 ≤9）。
    """
    out: List[Tuple[str, int]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in (" ", ",", "　"):
            i += 1
            continue
        if not (ch.isalnum()):
            raise ParseError(f"无法识别的字符：{ch!r}（位置 {i + 1}）")
        base = ch
        i += 1
        count = 1
        if i < n and text[i] in _SUB_SET:
            count = _SUBSCRIPTS[text[i]]
            i += 1
        elif i < n and text[i] == "_":
            # k_n 下划线形式（不带分隔符，仅在本段解析）
            j = i + 1
            j0 = j
            while j < n and text[j].isdigit():
                j += 1
            if j == j0:
                raise ParseError(f"下划线后缺少辆数（位置 {i + 1}）")
            count = int(text[j0:j])
            i = j
        if count <= 0:
            raise ParseError(f"车组 {base!r} 辆数须为正数")
        out.append((base, count))
    return out


def tokenize(raw: str) -> List[Tuple[str, int]]:
    """把原始串切为 [(raw_station, count)]。"""
    if not raw or not raw.strip():
        raise ParseError("待编车列为空")
    text = raw.strip()

    # 有分隔符：按空白/逗号切 token，逐个解析
    has_sep = any(ch.isspace() or ch == "," for ch in text)
    if has_sep:
        out: List[Tuple[str, int]] = []
        for tok in text.replace(",", " ").split():
            base = ""
            count = 1
            i = 0
            while i < len(tok):
                ch = tok[i]
                if ch == "_":
                    # _ 后面的数字是辆数
                    j = i + 1
                    j0 = j
                    while j < len(tok) and tok[j].isdigit():
                        j += 1
                    if j == j0:
                        raise ParseError(f"token {tok!r}：下划线后缺辆数")
                    count = int(tok[j0:j])
                    i = j
                    continue
                if ch in _SUB_SET:
                    count = _SUBSCRIPTS[ch]
                    i += 1
                    continue
                if ch.isspace():
                    i += 1
                    continue
                # 允许单 token 出现 "b2"? 不支持；多字符站名仅在带分隔符时逐 token 直接作站名
                if not ch.isalnum():
                    raise ParseError(f"无法识别的字符：{ch!r}（token {tok!r}）")
                base += ch
                i += 1
            if not base:
                raise ParseError(f"空车组 token：{tok!r}")
            if count <= 0:
                raise ParseError(f"车组 {base!r} 辆数须为正数")
            out.append((base, count))
        return out

    # 无分隔符
    if any(ch in _SUB_SET for ch in text) or "_" in text:
        return tokenize_attached_subscripts(text)
    # 纯字符：每字符一个去向，1 辆
    out = []
    for ch in text:
        if ch.isspace():
            continue
        if not ch.isalnum():
            raise ParseError(f"无法识别的字符：{ch!r}")
        out.append((ch, 1))
    return out


def assign_stations(tokens: List[Tuple[str, int]],
                    station_order: Optional[str] = None) -> List[Group]:
    """把 (raw_station, count) 转为 (station=站顺编号, count, pos)。

    - station_order 提供（如 "fedcba"）：raw 是字母/符号，按编成顺序从左到右编号 1..n；
    - 否则 raw 必须为数字：直接作为站顺号，并校验集合连续 1..max。
    """
    if not tokens:
        raise ParseError("待编车列为空")

    raws = [r for r, _ in tokens]
    if station_order is not None:
        order = [c for c in station_order.replace(" ", "").replace(",", "")
                 if c.isalnum()]
        seen: Dict[str, int] = {}
        rank: Dict[str, int] = {}
        for r in order:
            if r not in seen:
                seen[r] = len(rank) + 1
                rank[r] = len(rank) + 1
        if not rank:
            raise ParseError("station_order 为空")
        # 若同时出现数字与字母，数字优先按自身、字母按 rank？为避免歧义，要求全部能映射。
        missing = sorted({r for r in raws if r not in rank})
        if missing:
            raise ParseError(
                f"站名 {missing} 不在 station_order（编成顺序）{station_order!r} 中")
        stations = [rank[r] for r in raws]
        max_st = max(stations)
    else:
        nums: List[Optional[int]] = []
        for r in raws:
            if not r.isdigit():
                raise ParseError(
                    f"站名 {r!r} 不是数字；若用字母站名请提供 station_order（编成顺序）。")
            nums.append(int(r))
        stations = nums  # type: ignore[assignment]
        if not stations:
            raise ParseError("待编车列为空")
        max_st = max(stations)
        present = set(stations)
        if present != set(range(1, max_st + 1)):
            raise ParseError(
                f"去向编号应连续覆盖 1..{max_st}，实际为 {sorted(present)}")
    if max_st > 26:
        raise ParseError(f"去向编号过大（{max_st} > 26）")

    groups = [Group(st, c, i + 1) for i, (st, c) in enumerate(zip(stations, [c for _, c in tokens]))]
    return groups


def parse_seq(raw: str, station_order: Optional[str] = None) -> List[Group]:
    """解析待编车列字符串 → 车组列表（按书写序 远->机车端）。"""
    tokens = tokenize(raw)
    return assign_stations(tokens, station_order)


def groups_to_text(groups: List[Group]) -> str:
    """车组序列的紧凑文本（调试/展示用），如 "1₃4₁6₁…"。仅支持 <=9 辆与 <=9 站时带下标。"""
    def sub(n: int) -> str:
        return "" if n == 1 else chr(0x2080 + n) if 0 <= n <= 9 else f"_{n}"

    return "".join(f"{g.station}{sub(g.count)}" for g in groups)


# ---------------------------------------------------------------------------
# 例题 / 习题预设（前端按钮一键填充）
# keys 与 plan JSON 的输入字段一致。
# ---------------------------------------------------------------------------
PRESETS: Dict[str, Dict] = {
    "例4.3": {
        "seq": "b₂a₁c₁f₂e₁b₁f₂a₂c₁e₁d₂a₁",
        "station_order": "fedcba",
        "home_track": "10",
        "allowed_tracks": ["10", "11", "12", "13"],
        "depart_track": "DF3",
    },
    "例4.4": {
        "seq": "edgafbgfcea",
        "station_order": "gfedcba",
        "home_track": "12",
        "allowed_tracks": ["10", "11", "12", "13", "14"],
        "depart_track": "DF5",
    },
    "例4.6": {
        "seq": "4₂5₂6₁3₁5₂1₃2₁4₃3₂6₁5₁3₂1₁4₂7₂",
        "home_track": "7",
        "allowed_tracks": ["7", "8", "9", "10"],
        "depart_track": "DF3",
    },
    "习题2": {
        "seq": "1₃4₁6₁5₃1₂4₁3₁2₂6₂7₃",
        "home_track": "10",
        "track_budget": 5,
        "budget_includes_home": True,
        "depart_track": "DF5",
    },
    "习题3": {
        "seq": "3₁4₂7₃6₂1₃2₁5₃1₁3₂5₃3₁",
        "home_track": "10",
        "track_budget": 3,
        "budget_includes_home": True,
        "depart_track": "DF5",
    },
    "习题7": {
        "seq": "73652264135347",
        "home_track": "10",
        "depart_track": "DF5",
    },
    "习题8": {
        "seq": "659142481736",
        "home_track": "10",
        "depart_track": "DF5",
    },
    "习题9": {
        "seq": "835327144357664",
        "home_track": "10",
        "depart_track": "DF5",
    },
    "习题12": {
        "seq": "4₃3₂6₁2₁1₃5₂4₁2₂1₃6₂5₁4₁3₁",
        "home_track": "11",
        "allowed_tracks": ["11", "12", "13", "14"],
        "depart_track": "DF5",
    },
}
