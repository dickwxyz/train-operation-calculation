# -*- coding: utf-8 -*-
"""RAG 的路径、检索参数、LLM/embedding 配置。

链路：章节级 BM25 + bge-m3 向量（RRF 融合）→ 大模型严格依据教材片段组织答案。
"""

from __future__ import annotations

import os
from pathlib import Path

# 仓库根：scripts/rag/config.py -> parents[2]
ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "knowledge_base" / "铁路行车组织第2版-前3篇.md"

# ---- 模型与索引 ----
BGE_DIR = ROOT / "bge-m3"
BGE_ONNX = BGE_DIR / "onnx" / "model.onnx"
BGE_TOKENIZER = BGE_DIR / "tokenizer.json"
INDEX_DIR = ROOT / "rag_index"            # 用户要求：生成数据放仓库根目录，且不加入 .gitignore
EMBEDDING_DIM = 1024
EMBEDDING_MAX_LENGTH = 512                # chunk ≤ 900 字，512 token 足够
EMBEDDING_BATCH = 16

# ---- 分块参数（corpus.py） ----
CHILD_TARGET = 620
CHILD_MAX = 900
CHILD_OVERLAP = 90
EXAMPLE_MAX = 1800
MIN_CHUNK_CHARS = 60

# ---- 检索参数 ----
TOP_PARENTS = 3               # 取前几个 parent section 交给 LLM
PARENT_CHUNK_BUDGET = 4200    # 每个 parent 选入上下文的字符预算
MAX_CONTEXT_CHARS = 15000     # 总上下文预算
BM25_K1 = 1.5
BM25_B = 0.75

# RRF：向量为主（与 034 一致），BM25 为辅；多查询再做一次 RRF
RRF_K_VEC = 10
RRF_K_BM25 = 20
RRF_K_QUERY = 20
MIN_BM25_SCORE = 0.01       # 词面完全无命中时，只有足够强的向量相似才保留
MIN_VECTOR_ONLY = 0.55

# 标题命中加权（parent 级）
HEADING_BOOST = 0.15          # 每命中一级标题加 15%
STRUCTURE_BOOST = 1.25        # 含「步骤/第X步/包括/分为」的块

# ---- 查询改写（LLM） ----
QUERY_REWRITE = True
QUERY_REWRITE_MAX = 4
QUERY_REWRITE_MAX_TOKENS = 800
QUERY_REWRITE_TIMEOUT = 45

# ---- LLM ----
LLM_TIMEOUT = 120
LLM_MAX_TOKENS = 4000
LLM_TEMPERATURE = 0.2

# ---- 领域词（jieba 自定义词） ----
DOMAIN_WORDS = [
    "调车", "调车钩", "调车程", "调车作业计划", "调车表", "下落列", "可调车组",
    "邻组", "暂合列", "坐编", "驼峰", "牵出线", "推送调车法", "溜放调车法",
    "单推单溜", "双推单溜", "双推双溜", "解体调车", "编组调车", "摘挂调车",
    "取送调车", "调车机车", "调车领导人", "调车作业通知单", "钩计划",
    "接发列车", "闭塞设备", "电话闭塞法", "引导接车", "进路", "道岔",
    "货车集结", "集结车小时", "集结时间", "无改编通过", "有调中转车",
    "无调中转车", "改编能力", "改编车数", "取送车", "取送次数", "取送顺序",
    "车站作业计划", "班计划", "阶段计划", "调度指挥", "现在车",
    "货物列车编组计划", "列车编组计划", "编组站", "技术站", "区段站",
    "支点站", "车流径路", "车流", "直达列车", "技术直达列车", "始发直达列车",
    "阶梯直达列车", "基地直达列车", "空车直达列车", "装车地直达列车",
    "分组列车", "单组列车", "摘挂列车", "区段列车", "小运转列车",
    "绝对计算法", "表格计算法", "绝对条件", "必要条件", "充分条件",
    "目标函数", "车小时消耗", "节省时间", "T集", "t节", "F节", "F耗",
    "列车运行图", "运行图要素", "车站间隔时间", "追踪列车间隔时间",
    "区间通过能力", "平行运行图", "非平行运行图", "扣除系数", "旅行速度",
    "天窗", "自动闭塞", "半自动闭塞", "铁路运输能力",
    "单选题", "多选题", "选择题", "填空题", "判断题", "简答题", "计算题",
    "名词解释", "综合计算题", "多项选择题", "单项选择题", "判断分析题",
]

# 通用停用词（检索/查询改写时过滤；不是按题型写规则）
STOPWORDS = set("""
的 了 和 与 或 在 是 有 为 对 中 上 下 等 及 其 这 那 个 些 也 都 而 被 把 从 到 就
什么 如何 怎么 怎样 哪些 为什么 请 简述 简答 说明 试述 论述 分析 解释 包括 分别
主要 基本 可以 需要 进行 通过 根据 以及 一般 通常 就是 如果 因为 所以 但是 然后
""".split())


def _read_env(path: Path) -> dict[str, str]:
    """极简 .env 读取（KEY=VALUE；# 注释；去引号）。不打印任何值。"""
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def load_llm() -> dict[str, str]:
    """环境变量 > .env > 默认值。返回 {base_url, api_key, model}。"""
    env = _read_env(ROOT / ".env")
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return {
        "base_url": (env.get("LLM_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/"),
        "api_key": env.get("LLM_API_KEY", ""),
        "model": env.get("LLM_MODEL") or "deepseek-v4-flash",
    }
