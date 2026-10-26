# -*- coding: utf-8 -*-
"""
编组方案示意图（列车到达站图）生成器

把教材第十一章的示意图转写为 SCHEMES 条目，批量生成 SVG。
当前 SCHEMES 收录 13 张图：图 11.5、11.6.1、11.6.2、11.9.1–11.9.10。

统一图式（同线规则全程开启）：
  · 跨站直达车流按起点站由远到近占上方各行（A3 的先、A2 的后）；
  · 所有相邻站单位区段（3→2、2→1、1→0）合并到同一行作主链，放最后一行。
节点索引约定：索引 i → 站号 (n-1-i)
  4 个车站：0/1/2/3 → 3/2/1/0

用法：
    python draw_scheme.py
产物（默认只输出 .svg，落在本脚本所在目录）：
    11.5.svg、11.6.1.svg、11.6.2.svg、11.9.1.svg … 11.9.10.svg
画布上只画线段、起点竖线标记、数学标注与底部站点编号；
不生成任何方案编号、方框、罗马数字等原图自带标记。

依赖：
  cairosvg + numpy + pillow 为可选（像素级自检）。
  缺失时仍生成 SVG，只跳过像素自检，结构校验照常执行。
"""

import io
import os

# 光栅自检（cairosvg + numpy + pillow）为可选依赖：
# 缺失时仍能生成 SVG，只跳过像素级自检与标注实测宽度。
try:
    import cairosvg
    import numpy as np
    from PIL import Image
    HAVE_RASTER = True
except ImportError:
    HAVE_RASTER = False

# 输出目录 = 本脚本所在目录（SVG 落在代码旁边）
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================ 一、全局几何参数
FONT = "Times New Roman, Times, Liberation Serif, DejaVu Serif, serif"

CONFIG = {
    "W": 950,           # 画布宽（同时作 viewBox，1:1 不缩放）
    "X0": 165,          # 节点 0 的 x（默认；已移除标题，新方案可设 x0 覆盖）
    "DX": 212,          # 单区段长度上限；车站变多时自动收窄（见 AUTO_FIT）
    "RIGHT_PAD": 40,    # 右侧安全边距，自动收窄时保留
    "AUTO_FIT": True,   # True：车站数 > 4 时自动收窄 DX，保证末端不出画布
    "SAVE_PNG": False,  # 只输出 SVG（自检仍在内存中光栅化，不落盘）
    "TOP_PAD": 95,      # 第 0 行的 y
    "ROW_GAP": 130,     # 行间距（方案 I 用 130；多行图可按需调小）
    "BOTTOM_PAD": 85,   # 末行到画布底的距离
    "LW": 2.2,          # 线宽（横线与竖线标记统一）
    "TICK": 11,         # 起点竖线标记半高（上下各 11）
    "LAB_SIZE": 23,     # 标注字号
    "LAB_GAP": 14,      # 标注基线到横线的垂直间距
    "LAB_DX": 4,        # 标注相对起点竖线的水平偏移
    "SUB_RATIO": 0.62,  # 下标字号 / 正文字号
    "STATION_DY": 30,   # 站点编号相对末行的下沉距离
    "STATION_SIZE": 23,     # 站点编号字号

    # 第 7 条规则开关：相邻车站开行的列车必须同线。画非编组类示意图时置 False
    "STRICT_CHAIN": True,
}

# ============================================================ 二、方案定义
# 每条线: {"row": 行号, "from": 起点节点索引, "to": 终点节点索引, "terms": 下标元组}
# 节点索引 0/1/2/3 对应技术站 3/2/1/0（索引 i → 站号 3-i）

# 早期开发用的方案（保留备查，不参与渲染）
LEGACY_SCHEMES = [
    {
        "name": "scheme_I",          # 回归基准：与已确认版逐像素一致
        "row_gap": 130,
        "stations": None,
        "lines": [
            {"row": 0, "from": 0, "to": 3, "terms": ("30",)},
            {"row": 1, "from": 0, "to": 1, "terms": ("32", "31")},
            {"row": 1, "from": 1, "to": 2, "terms": ("21", "20", "31")},
            {"row": 1, "from": 2, "to": 3, "terms": ("10", "20")},
        ],
    },
    {
        # 定稿：相邻车站开行的列车（3→2、2→1、1→0）必须同线，构成首尾相接的主链；
        #       只有跨站直达（2→0）才另起一行。
        "name": "scheme_II",
        "row_gap": 80,
        "stations": None,
        "lines": [
            {"row": 0, "from": 1, "to": 3, "terms": ("20", "30")},   # 2→0 直达（跨站，独占一行）
            {"row": 1, "from": 0, "to": 1, "terms": ("32", "30")},   # 3→2
            {"row": 1, "from": 1, "to": 2, "terms": ("21",)},          # 2→1
            {"row": 1, "from": 2, "to": 3, "terms": ("10",)},          # 1→0
        ],
    },
    {
        # ★ 5 个车站（4/3/2/1/0）定稿：节点索引 0..4 → 站号 4/3/2/1/0（索引 i → 4-i）
        #   首行下标原图误标为 N₂₀，实为 N₄₀（4→0 直达，最长），已按正确值 40 处理。
        #   原图上方那段不完整的水平线为裁切残留，不绘制。
        "name": "scheme_IV",
        "row_gap": 80,
        "x0": 80,
        "stations": "auto",          # 自动生成 4/3/2/1/0
        "lines": [
            {"row": 0, "from": 0, "to": 4, "terms": ("40",)},        # 4→0 直达（最长）
            {"row": 1, "from": 0, "to": 2, "terms": ("42", "40")},   # 4→2：N₄₀ 随此车到 2 站改编
            {"row": 2, "from": 1, "to": 4, "terms": ("30",)},        # 3→0
            {"row": 3, "from": 2, "to": 4, "terms": ("20", "40")},   # 2→0：接续改编后的 N₄₀
        ],
    },
    {
        "name": "scheme_II_full",    # 定稿版 + 站点编号（交付形态）
        "row_gap": 80,
        "stations": ["3", "2", "1", "0"],
        "lines": [
            {"row": 0, "from": 1, "to": 3, "terms": ("20", "30")},
            {"row": 1, "from": 0, "to": 1, "terms": ("32", "30")},
            {"row": 1, "from": 1, "to": 2, "terms": ("21",)},
            {"row": 1, "from": 2, "to": 3, "terms": ("10",)},
        ],
    },
    {
        # 方案 III：3 站分别开行直达 0 / 直达 1 / 区段 2，下方为接续主链
        "name": "scheme_III",
        "row_gap": 80,
        "stations": None,
        "lines": [
            {"row": 0, "from": 0, "to": 3, "terms": ("30",)},   # 3→0 直达（最长）
            {"row": 1, "from": 0, "to": 2, "terms": ("31",)},   # 3→1 直达（次长）
            {"row": 2, "from": 0, "to": 1, "terms": ("32",)},        # 3→2（主链首段）
            {"row": 2, "from": 1, "to": 2, "terms": ("20", "21")},   # 2→1
            {"row": 2, "from": 2, "to": 3, "terms": ("10", "20")},   # 1→0
        ],
    },
    {
        "name": "scheme_III_full",   # 方案 III + 站点编号 + 标题
        "row_gap": 80,
        "stations": ["3", "2", "1", "0"],
        "lines": [
            {"row": 0, "from": 0, "to": 3, "terms": ("30",)},
            {"row": 1, "from": 0, "to": 2, "terms": ("31",)},
            {"row": 2, "from": 0, "to": 1, "terms": ("32",)},
            {"row": 2, "from": 1, "to": 2, "terms": ("20", "21")},
            {"row": 2, "from": 2, "to": 3, "terms": ("10", "20")},
        ],
    },
]


# ============================================================ 二、方案定义（13 张教材图）
# 统一图式：跨站直达车流按起点站由远到近占上方各行（A3 的先、A2 的后）；
#          所有相邻站单位区段（3→2、2→1、1→0）合并到同一行作主链，放最后一行。
# 节点索引 0/1/2/3 = 车站 3/2/1/0；stations="auto" → 底部站号 3/2/1/0。

SCHEMES = [
    # 图11.5 原始车流图：三支直达 + 主链
    {"name": "11.5", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("30",)},
        {"row": 1, "from": 0, "to": 2, "terms": ("31",)},
        {"row": 2, "from": 1, "to": 3, "terms": ("20",)},
        {"row": 3, "from": 0, "to": 1, "terms": ("32",)},
        {"row": 3, "from": 1, "to": 2, "terms": ("21",)},
        {"row": 3, "from": 2, "to": 3, "terms": ("10",)},
    ]},
    # 图11.6 方案 I（2+1,0;1+0;0）
    {"name": "11.6.1", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("30",)},
        {"row": 1, "from": 0, "to": 1, "terms": ("32", "31")},
        {"row": 1, "from": 1, "to": 2, "terms": ("21", "20", "31")},
        {"row": 1, "from": 2, "to": 3, "terms": ("10", "20")},
    ]},
    # 图11.6 方案 II（2+0,1;1,0;0）
    {"name": "11.6.2", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 2, "terms": ("31",)},
        {"row": 1, "from": 1, "to": 3, "terms": ("20", "30")},
        {"row": 2, "from": 0, "to": 1, "terms": ("32", "30")},
        {"row": 2, "from": 1, "to": 2, "terms": ("21",)},
        {"row": 2, "from": 2, "to": 3, "terms": ("10",)},
    ]},
    # 图11.9 方案① 0,1,2;0,1;0
    {"name": "11.9.1", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("30",)},
        {"row": 1, "from": 0, "to": 2, "terms": ("31",)},
        {"row": 2, "from": 1, "to": 3, "terms": ("20",)},
        {"row": 3, "from": 0, "to": 1, "terms": ("32",)},
        {"row": 3, "from": 1, "to": 2, "terms": ("21",)},
        {"row": 3, "from": 2, "to": 3, "terms": ("10",)},
    ]},
    # 方案② 0,1+2;0,1;0
    {"name": "11.9.2", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("30",)},
        {"row": 1, "from": 1, "to": 3, "terms": ("20",)},
        {"row": 2, "from": 0, "to": 1, "terms": ("31", "32")},
        {"row": 2, "from": 1, "to": 2, "terms": ("21", "31")},
        {"row": 2, "from": 2, "to": 3, "terms": ("10",)},
    ]},
    # 方案③ 0+1,2;0,1;0
    {"name": "11.9.3", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 2, "terms": ("30", "31")},
        {"row": 1, "from": 1, "to": 3, "terms": ("20",)},
        {"row": 2, "from": 0, "to": 1, "terms": ("32",)},
        {"row": 2, "from": 1, "to": 2, "terms": ("21",)},
        {"row": 2, "from": 2, "to": 3, "terms": ("10", "30")},
    ]},
    # 方案④ 0+2,1;0,1;0
    {"name": "11.9.4", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 2, "terms": ("31",)},
        {"row": 1, "from": 1, "to": 3, "terms": ("20", "30")},
        {"row": 2, "from": 0, "to": 1, "terms": ("30", "32")},
        {"row": 2, "from": 1, "to": 2, "terms": ("21",)},
        {"row": 2, "from": 2, "to": 3, "terms": ("10",)},
    ]},
    # 方案⑤ 0+1+2;0,1;0
    {"name": "11.9.5", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 1, "to": 3, "terms": ("20", "30")},
        {"row": 1, "from": 0, "to": 1, "terms": ("30", "31", "32")},
        {"row": 1, "from": 1, "to": 2, "terms": ("21", "31")},
        {"row": 1, "from": 2, "to": 3, "terms": ("10",)},
    ]},
    # 方案⑥ 0,1,2;0+1;0 —— 与 md 的 example 相同
    {"name": "11.9.6", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("30",)},
        {"row": 1, "from": 0, "to": 2, "terms": ("31",)},
        {"row": 2, "from": 0, "to": 1, "terms": ("32",)},
        {"row": 2, "from": 1, "to": 2, "terms": ("20", "21")},
        {"row": 2, "from": 2, "to": 3, "terms": ("10", "20")},
    ]},
    # 方案⑦ 0,1+2;0+1;0
    {"name": "11.9.7", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("30",)},
        {"row": 1, "from": 0, "to": 1, "terms": ("31", "32")},
        {"row": 1, "from": 1, "to": 2, "terms": ("20", "21", "31")},
        {"row": 1, "from": 2, "to": 3, "terms": ("10", "20")},
    ]},
    # 方案⑧ 0+1,2;0+1;0
    {"name": "11.9.8", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 2, "terms": ("30", "31")},
        {"row": 1, "from": 0, "to": 1, "terms": ("32",)},
        {"row": 1, "from": 1, "to": 2, "terms": ("20", "21")},
        {"row": 1, "from": 2, "to": 3, "terms": ("10", "20", "30")},
    ]},
    # 方案⑨ 0+2,1;0+1;0
    {"name": "11.9.9", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 2, "terms": ("31",)},
        {"row": 1, "from": 0, "to": 1, "terms": ("30", "32")},
        {"row": 1, "from": 1, "to": 2, "terms": ("20", "21", "30")},
        {"row": 1, "from": 2, "to": 3, "terms": ("10", "20", "30")},
    ]},
    # 方案⑩ 0+1+2;0+1;0（单行三连）
    {"name": "11.9.10", "row_gap": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 1, "terms": ("30", "31", "32")},
        {"row": 0, "from": 1, "to": 2, "terms": ("20", "21", "30", "31")},
        {"row": 0, "from": 2, "to": 3, "terms": ("10", "20", "30")},
    ]},
    # 图11.23 例11.6 最佳方案（5 个车站 4/3/2/1/0）
    # 1→0 中间那团涂改按语义判定为划掉的项，实际为 N10+N40
    {"name": "11.23", "row_gap": 80, "x0": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("40", "41")},   # 4→1
        {"row": 1, "from": 2, "to": 4, "terms": ("30", "20")},   # 2→0
        {"row": 2, "from": 0, "to": 1, "terms": ("43", "42")},   # 4→3
        {"row": 2, "from": 1, "to": 2, "terms": ("32", "42", "31", "30")},  # 3→2
        {"row": 2, "from": 2, "to": 3, "terms": ("21", "31")},   # 2→1
        {"row": 2, "from": 3, "to": 4, "terms": ("10", "40")},   # 1→0
    ]},
    # 图11.20 例11.6 初始方案
    {"name": "11.20", "row_gap": 80, "x0": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("41",)},        # 4→1
        {"row": 1, "from": 0, "to": 2, "terms": ("42", "40")},   # 4→2
        {"row": 2, "from": 1, "to": 4, "terms": ("30",)},        # 3→0
        {"row": 3, "from": 2, "to": 4, "terms": ("20", "40")},   # 2→0
        {"row": 4, "from": 0, "to": 1, "terms": ("43",)},        # 4→3
        {"row": 4, "from": 1, "to": 2, "terms": ("32", "31")},   # 3→2
        {"row": 4, "from": 2, "to": 3, "terms": ("21", "31")},   # 2→1
        {"row": 4, "from": 3, "to": 4, "terms": ("10",)},        # 1→0
    ]},
    # 图11.21 例11.6 过渡方案 I
    {"name": "11.21", "row_gap": 80, "x0": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("40", "41")},   # 4→1
        {"row": 1, "from": 1, "to": 4, "terms": ("30",)},        # 3→0
        {"row": 2, "from": 2, "to": 4, "terms": ("20",)},        # 2→0
        {"row": 3, "from": 0, "to": 1, "terms": ("42", "43")},   # 4→3
        {"row": 3, "from": 1, "to": 2, "terms": ("32", "31")},   # 3→2
        {"row": 3, "from": 2, "to": 3, "terms": ("21", "31")},   # 2→1
        {"row": 3, "from": 3, "to": 4, "terms": ("10", "40")},   # 1→0
    ]},
    # 图11.22 例11.6 过渡方案 II
    {"name": "11.22", "row_gap": 80, "x0": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 3, "terms": ("40", "41")},   # 4→1
        {"row": 1, "from": 1, "to": 3, "terms": ("30", "31")},   # 3→1
        {"row": 2, "from": 2, "to": 4, "terms": ("20",)},        # 2→0
        {"row": 3, "from": 0, "to": 1, "terms": ("42", "43")},   # 4→3
        {"row": 3, "from": 1, "to": 2, "terms": ("32",)},        # 3→2
        {"row": 3, "from": 2, "to": 3, "terms": ("21", "31")},   # 2→1
        {"row": 3, "from": 3, "to": 4, "terms": ("10", "40")},   # 1→0
    ]},
    # 习题2 最优方案（5 站）
    {"name": "xt2", "row_gap": 80, "x0": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 4, "terms": ("40",)},        # 4→0
        {"row": 1, "from": 0, "to": 2, "terms": ("41", "42")},   # 4→2
        {"row": 2, "from": 1, "to": 4, "terms": ("30",)},        # 3→0
        {"row": 3, "from": 2, "to": 4, "terms": ("20",)},        # 2→0
        {"row": 4, "from": 0, "to": 1, "terms": ("43",)},        # 4→3
        {"row": 4, "from": 1, "to": 2, "terms": ("32", "31")},   # 3→2
        {"row": 4, "from": 2, "to": 3, "terms": ("21", "41", "31")},  # 2→1
        {"row": 4, "from": 3, "to": 4, "terms": ("10",)},        # 1→0
    ]},
    # 习题3 最优方案（5 站）
    {"name": "xt3", "row_gap": 80, "x0": 80, "stations": "auto", "lines": [
        {"row": 0, "from": 0, "to": 2, "terms": ("40", "41", "42")},  # 4→2
        {"row": 1, "from": 2, "to": 4, "terms": ("20", "30", "40")},  # 2→0
        {"row": 2, "from": 0, "to": 1, "terms": ("43",)},        # 4→3
        {"row": 2, "from": 1, "to": 2, "terms": ("32", "31", "30")},  # 3→2
        {"row": 2, "from": 2, "to": 3, "terms": ("21", "41", "31")},  # 2→1
        {"row": 2, "from": 3, "to": 4, "terms": ("10",)},        # 1→0
    ]},
]


# 已被否定的候选（按“相邻开行同线”规则排除），保留供对照
REJECTED = [
    {
        # 错：把 1→0 的 N₁₀ 单独放一行，割裂了主链
        "name": "scheme_II_wrong_split",
        "row_gap": 80,
        "stations": None,
        "lines": [
            {"row": 0, "from": 1, "to": 3, "terms": ("20", "30")},
            {"row": 1, "from": 0, "to": 1, "terms": ("32", "30")},
            {"row": 1, "from": 1, "to": 2, "terms": ("21",)},
            {"row": 2, "from": 2, "to": 3, "terms": ("10",)},
        ],
    },
    {
        # 错：四条线各占一行，看不出接续关系
        "name": "scheme_II_wrong_stack",
        "row_gap": 80,
        "stations": None,
        "lines": [
            {"row": 0, "from": 0, "to": 1, "terms": ("32", "30")},
            {"row": 1, "from": 1, "to": 3, "terms": ("20", "30")},
            {"row": 2, "from": 1, "to": 2, "terms": ("21",)},
            {"row": 3, "from": 2, "to": 3, "terms": ("10",)},
        ],
    },
]

# ============================================================ 三、图元构件


def head(w, h):
    """画布 + 箭头 marker。

    要点：
    - markerUnits="userSpaceOnUse"：箭头大小为固定用户单位，不随 stroke-width 缩放；
    - refX=9.5：箭尖正好落在线段终点（不越出也不缩回）；
    - orient="auto-start-reverse"：箭头随线段方向旋转；老旧渲染器不支持时改 "auto"。
    """
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <defs>
    <marker id="ar" viewBox="0 0 10 10" refX="9.5" refY="5"
            markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse"
            orient="auto-start-reverse">
      <path d="M0,1.2 L10,5 L0,8.8 z" fill="#000"/>
    </marker>
  </defs>
  <rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>
'''


def arrow(x1, y1, x2, y2, w=None):
    """带箭头的水平线段。"""
    w = w or CONFIG["LW"]
    return (f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#000" '
            f'stroke-width="{w}" marker-end="url(#ar)"/>')


def tick(x, y, half=None, w=None):
    """起点竖线标记：垂直穿过水平线，上下各 half。"""
    half = half or CONFIG["TICK"]
    w = w or CONFIG["LW"]
    return (f'  <line x1="{x}" y1="{y-half}" x2="{x}" y2="{y+half}" '
            f'stroke="#000" stroke-width="{w}"/>')


def expr(x, y, terms, size=None, anchor="start"):
    """数学式标注，如 N₃₂+N₃₁：斜体 N + 小字号下标。

    关键坑：tspan 用 dy 压低下标后，必须再用负 dy 复位，
    否则后面的 “+” 和下一个 N 会跟着一起下沉。
    """
    size = size or CONFIG["LAB_SIZE"]
    sub = int(size * CONFIG["SUB_RATIO"])
    parts = []
    for i, t in enumerate(terms):
        if i:
            parts.append('<tspan font-style="normal">+</tspan>')
        parts.append('<tspan font-style="italic">N</tspan>'
                     f'<tspan font-size="{sub}" dy="{size*0.24:.1f}" '
                     f'font-style="normal">{t}</tspan>'
                     f'<tspan dy="-{size*0.24:.1f}"> </tspan>')
    return (f'  <text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'text-anchor="{anchor}" fill="#000">' + ''.join(parts) + '</text>')


def label(x, y, text, size=None, anchor="middle"):
    """普通文字（仅用于底部站点编号）。

    注：早期版本曾用它在左上角画“方案 I / II / III”标题，
    按需求已移除——方案编号属于原图标记，不在生成范围内。
    """
    size = size or CONFIG["STATION_SIZE"]
    return (f'  <text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'text-anchor="{anchor}" fill="#000">{text}</text>')


def est_width(terms, size=None):
    """实测标注宽度：渲染一次该 text，量包围盒。

    比按 em 估算可靠——衬线字体下 N₃₂ 的实际宽度与估算偏差可达 30%。
    用于自检同排标注是否重叠（标注改成左对齐后最易踩的坑）。
    """
    size = size or CONFIG["LAB_SIZE"]
    if not HAVE_RASTER:
        # 无 cairosvg 时用近似宽度：每项约 1.35em（N+下标），加号约 0.6em
        return int(len(terms) * size * 1.35 + (len(terms) - 1) * size * 0.6)
    svg = head(2000, 200) + expr(10, 100, terms, size=size) + "\n</svg>"
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), scale=1,
                           background_color="white")
    a = np.array(Image.open(io.BytesIO(png)).convert("L")) < 128
    cols = np.where(a.any(axis=0))[0]
    return int(cols.max() - cols.min() + 1) if len(cols) else 0


# ============================================================ 四、组装
def geometry(scheme):
    """算出节点 x、各行 y、画布高。

    车站数不再写死为 4：
    - n_node 由线路起终点（或 stations 列表长度）推导，支持任意个车站；
    - n_node > 4 时按可用宽度自动收窄 DX，避免末端箭头冲出画布。
      5 个车站时 DX: 212 → 186，末端 x=909，仍在画布内。
    """
    c = CONFIG
    n_from_lines = max(max(l["from"], l["to"]) for l in scheme["lines"]) + 1
    st = scheme.get("stations")
    n_node = max(n_from_lines, len(st) if isinstance(st, list) else 0)

    x0 = scheme.get("x0", c["X0"])
    dx = scheme.get("dx", c["DX"])
    if c["AUTO_FIT"] and n_node > 1:
        avail = c["W"] - x0 - c["RIGHT_PAD"]
        dx = min(dx, avail / (n_node - 1))

    xs = [x0 + i * dx for i in range(n_node)]
    gap = scheme.get("row_gap", c["ROW_GAP"])
    max_row = max(l["row"] for l in scheme["lines"])
    ys = {r: c["TOP_PAD"] + r * gap for r in range(max_row + 1)}
    h = c["TOP_PAD"] + max_row * gap + c["BOTTOM_PAD"]
    return xs, ys, h


def station_labels(scheme, xs):
    """站点编号列表；"auto" 时按 n..0 自动生成（5 站 → 4,3,2,1,0）。"""
    st = scheme.get("stations")
    if isinstance(st, list):
        return st
    if st == "auto":
        n = len(xs)
        return [str(n - 1 - i) for i in range(n)]
    return None


def build(scheme):
    c = CONFIG
    xs, ys, h = geometry(scheme)
    b = []

    # 每条线：横线 → 起点竖线标记 → 横线上方的标注（左对齐、与竖线对齐）
    for l in scheme["lines"]:
        x1, x2, y = xs[l["from"]], xs[l["to"]], ys[l["row"]]
        b.append(arrow(x1, y, x2, y))
        b.append(tick(x1, y))
        b.append(expr(x1 + c["LAB_DX"], y - c["LAB_GAP"], l["terms"]))

    # 可选：站点编号（画在末行下方）
    st = station_labels(scheme, xs)
    if st:
        y_last = max(ys.values())
        for x, s in zip(xs, st):
            b.append(label(x, y_last + c["STATION_DY"], s, size=c["STATION_SIZE"]))

    return head(c["W"], h) + "\n".join(b) + "\n</svg>"


# ============================================================ 五、自检
def check_chain(scheme):
    """第 7 条构图规则校验：相邻车站开行的列车必须同线，构成一条完整主链。

    判定：
    - 所有「单位区段」线（to == from + 1）必须落在同一行；
    - 这些区段必须首尾相接、连续覆盖 0→1→2→…→n-1，不留缝隙；
    - 跨站直达线（跨度 > 1）不得与主链同行，否则视觉上混淆接续关系。
    """
    units = sorted([l for l in scheme["lines"] if l["to"] == l["from"] + 1],
                   key=lambda l: l["from"])
    if not units:
        return True
    ok = True

    rows = {l["row"] for l in units}
    if len(rows) > 1:
        ok = False
        detail = ", ".join(f"{l['from']}→{l['to']}@row{l['row']}" for l in units)
        print(f"  ⚠ 主链未同线: 相邻区段分散在第 {sorted(rows)} 行 ({detail})")
        print(f"      → 相邻车站开行的列车必须画在同一行")

    for p, q in zip(units, units[1:]):
        if p["to"] != q["from"]:
            ok = False
            print(f"  ⚠ 主链断裂: {p['from']}→{p['to']} 之后接 {q['from']}→{q['to']}")

    chain_row = next(iter(rows))
    for l in scheme["lines"]:
        if l["to"] - l["from"] > 1 and l["row"] == chain_row:
            ok = False
            print(f"  ⚠ 跨站直达线 {l['from']}→{l['to']} 与主链同行（应另起一行）")
    return ok


def check(svg, scheme):
    """校验：有 cairosvg 时做像素级检查；否则只做结构检查。

    像素级部分验证横线条数、起点竖线、内容是否越界；
    无论是否安装 cairosvg，都会做同线规则、行内连续与标注重叠检查。
    """
    ok = True
    xs, ys, _ = geometry(scheme)
    n_expect = len({l["row"] for l in scheme["lines"]})

    if HAVE_RASTER:
        png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), scale=2,
                               background_color="white")
        a = np.array(Image.open(io.BytesIO(png)).convert("L")) < 128
        h, w = a.shape

        # 横线：把连续像素行聚成一条（线宽 2.2 × scale 2 ≈ 4 个像素行）
        rows = [y for y, cnt in enumerate(a.sum(axis=1)) if cnt > w * 0.12]
        groups = []
        for y in rows:
            if groups and y - groups[-1][-1] <= 3:
                groups[-1].append(y)
            else:
                groups.append([y])
        # 同一行的多段首尾相接 → 像素上算一条
        if len(groups) != n_expect:
            ok = False
        print(f"  横线: 检出 {len(groups)} 条 (期望 {n_expect}) "
              f"中心 y={[round(sum(g)/len(g)/2, 1) for g in groups]}")

        for l in scheme["lines"]:
            # AUTO_FIT 后 xs 可能是小数，索引需取整
            col = int(round(xs[l["from"]] * 2))
            span = int(a[:, col].sum())
            if span < 30:
                ok = False
        print(f"  起点竖线: {len(scheme['lines'])} 条全部存在"
              if ok else "  起点竖线: 有缺失")

        cols = np.where(a.any(axis=0))[0]
        print(f"  内容 x 范围: {cols.min()//2}–{cols.max()//2} (画布宽 {CONFIG['W']})")
        if cols.max() // 2 > CONFIG["W"] - 5:
            ok = False
    else:
        print(f"  横线: 预期 {n_expect} 条（未安装 cairosvg，跳过像素自检）")

    # 规则校验（第 7 条）：相邻车站开行的列车必须同线，构成一条完整主链
    if CONFIG["STRICT_CHAIN"]:
        ok_chain = check_chain(scheme)
        ok = ok and ok_chain

    by_row = {}
    for l in scheme["lines"]:
        by_row.setdefault(l["row"], []).append(l)
    for r, ls in sorted(by_row.items()):
        ls = sorted(ls, key=lambda l: l["from"])
        if len(ls) > 1:
            for p, q in zip(ls, ls[1:]):
                if p["to"] != q["from"]:
                    ok = False
                    print(f"  ⚠ 第 {r} 行线段不连续: {p['from']}→{p['to']} 之后接 "
                          f"{q['from']}→{q['to']}（相邻车站开行的列车必须同线且首尾相接）")

        # 同排标注是否重叠（左对齐后最易踩的坑）
        for p, q in zip(ls, ls[1:]):
            end_p = xs[p["from"]] + est_width(p["terms"])
            start_q = xs[q["from"]]
            if end_p > start_q - 6:
                ok = False
                print(f"  ⚠ 第 {r} 排标注重叠: 右端 {end_p:.0f} > 下一标注起点 {start_q}")
    print("  自检:", "通过" if ok else "未通过")
    return ok


def save(svg, name):
    """落盘。SAVE_PNG=False 时只写 SVG（自检仍在内存中光栅化）。"""
    p_svg = os.path.join(OUT_DIR, f"{name}.svg")
    with open(p_svg, "w", encoding="utf-8") as f:
        f.write(svg)
    if not CONFIG["SAVE_PNG"]:
        return p_svg, None
    p_png = os.path.join(OUT_DIR, f"{name}.png")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=p_png,
                     scale=2, background_color="white")
    return p_svg, p_png


RENDER_REJECTED = False      # 置 True 可一并渲染反例，用于对照检查

if __name__ == "__main__":
    for scheme in SCHEMES:
        svg = build(scheme)
        p_svg, p_png = save(svg, scheme["name"])
        print(f"[{scheme['name']}] -> {p_svg}, {p_png}")
        check(svg, scheme)

    if RENDER_REJECTED:
        print("\n--- 反例（应报“线段不连续”）---")
        for scheme in REJECTED:
            svg = build(scheme)
            save(svg, scheme["name"])
            print(f"[{scheme['name']}]")
            check(svg, scheme)

    # 回归：方案 I 必须与已确认版逐像素一致（基准文件不存在时自动跳过）
    ref_path = os.path.join(OUT_DIR, "scheme_alt.svg")
    new_path = os.path.join(OUT_DIR, "scheme_I.svg")
    if HAVE_RASTER and os.path.exists(ref_path) and os.path.exists(new_path):
        try:
            ref = open(ref_path, encoding="utf-8").read()
            new = open(new_path, encoding="utf-8").read()

            def px(s):
                return np.array(Image.open(io.BytesIO(
                    cairosvg.svg2png(bytestring=s.encode(), scale=2,
                                     background_color="white"))).convert("L"))

            a, b = px(ref), px(new)
            same = a.shape == b.shape and (a == b).all()
            print(f"\n回归比对（方案 I vs 已确认版）: {'一致' if same else '不一致'}"
                  f"，差异像素 {int((a != b).sum()) if a.shape == b.shape else '尺寸不同'}")
        except FileNotFoundError:
            print("\n回归比对: 未找到基准文件，已跳过")
    else:
        print("\n回归比对: 基准文件或 cairosvg 不可用，已跳过")
