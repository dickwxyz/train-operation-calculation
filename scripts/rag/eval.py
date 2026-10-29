# -*- coding: utf-8 -*-
"""RAG 检索回归评测。

默认离线：只走章节级混合检索，不调用大模型。
    venv/bin/python -m scripts.rag.eval
可选 LLM 烟测（3 条，会真实调用模型）：
    venv/bin/python -m scripts.rag.eval --with-llm
"""

from __future__ import annotations

import argparse
import re
import sys

from . import qa, retriever
from .embedding import BgeM3Embedder
from .vector import NullVectorBackend, NumpyVectorBackend

# (问题, 期望关键词（任一命中即可）, 是否教材外问题)
CASES: list[tuple[str, list[str], bool]] = [
    ("什么是调车钩？", ["调车钩"], False),
    ("调车程与调车钩有什么区别？", ["调车程", "调车钩"], False),
    ("调车工作“九固定”包括哪些？", ["九固定", "固定作业区域"], False),
    ("驼峰按线路配置分为哪几类？", ["驼峰"], False),
    ("简述调车作业计划的编制步骤", ["调车作业计划", "下落", "调整", "合并"], False),
    ("调车作业计划如何编制？", ["下落", "调整", "合并", "编写"], False),
    ("什么是下落、调整、合并？", ["下落", "调整", "合并"], False),
    ("例4.3的调车作业计划怎么编？", ["例 4.3", "例4.3", "调车表"], False),
    ("调车钩是衡量____的基本单位", ["调车钩", "基本单位"], False),
    ("下列属于调车工作的有（ ） A. 解体调车 B. 编组调车 C. 摘挂调车 D. 取送调车 E. 列车运行",
     ["调车工作的分类", "解体调车", "编组调车"], False),
    ("货车集结时间怎么计算？", ["集结时间", "集结车小时"], False),
    ("什么是货车集结车小时？", ["集结车小时"], False),
    ("合理取送次数如何确定？", ["取送次数"], False),
    ("车站各子系统工作的协调条件有哪些？", ["协调"], False),
    ("车站班计划包括哪些内容？", ["班计划"], False),
    ("货物列车编组计划的任务是什么？", ["编组计划", "任务"], False),
    ("货物列车如何分类？", ["货物列车", "分类"], False),
    ("车流径路选择的影响因素有哪些？", ["车流径路"], False),
    ("装车地直达列车的适用条件有哪些？", ["装车地直达"], False),
    ("什么是绝对条件、必要条件、充分条件？", ["绝对条件", "必要条件", "充分条件"], False),
    ("表格计算法的三个判别条件是什么？", ["必要条件", "充分条件", "判别条件"], False),
    ("表格计算法的步骤有哪些？", ["表格计算法"], False),
    ("例11.3怎么用表格计算法求解？", ["例 11.3", "例11.3", "表格计算法"], False),
    ("分组列车的特点与利弊是什么？", ["分组列车"], False),
    ("列车编组计划如何最终确定？", ["列车编组计划", "检查"], False),
    ("列车运行图如何分类？", ["运行图"], False),
    ("车站间隔时间包括哪些？", ["车站间隔时间"], False),
    ("追踪列车间隔时间怎么计算？", ["追踪列车间隔"], False),
    ("平行运行图通过能力怎么算？", ["平行运行图", "通过能力"], False),
    ("非平行运行图通过能力怎么算？", ["非平行运行图", "扣除系数"], False),
    ("加强铁路通过能力的途径有哪些？", ["运输能力", "加强"], False),
    ("什么是坐编？", ["坐编"], False),
    ("调车工作的基本要求是什么？", ["调车工作的要求", "基本要求"], False),
    ("今天天气怎么样？", [], True),
]


def _backend():
    vec = NumpyVectorBackend()
    if not vec.available or not BgeM3Embedder().available():
        print("警告：rag_index/ 或 bge-m3/ 不可用，本次仅用 BM25 检索。"
              "运行 python -m scripts.rag.build_index 可启用向量。")
        return NullVectorBackend()
    return vec


def _hay(result) -> str:
    parts = []
    for h in result.parents:
        parts.extend(h.parent.heading_path)
        parts.append(h.parent.text)
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-llm", action="store_true", help="额外跑 3 条真实 LLM 烟测")
    args = ap.parse_args()
    backend = _backend()

    rows = []
    hit_ok = cite_ok = 0
    for question, expect, out_of_scope in CASES:
        result = retriever.search(question, vector_backend=backend)
        if out_of_scope:
            ok = not result.parents
            cite = ok
        else:
            hay = _hay(result)
            ok = any(e in hay for e in expect)
            cite = bool(result.parents) and all(
                h.chunks and qa._page_label(h.chunks) for h in result.parents)
        hit_ok += 1 if ok else 0
        cite_ok += 1 if cite else 0
        rows.append((question, ok, cite, out_of_scope,
                     result.parents[0].parent.heading_path if result.parents else []))

    print("%-2s %-4s %-4s %-8s %s" % ("#", "检索", "出处", "教材外", "问题 / 首条命中"))
    for i, (q, ok, cite, out, path) in enumerate(rows, 1):
        print("%-2d %-4s %-4s %-8s %s  →  %s" % (
            i, "✓" if ok else "✗", "✓" if cite else "✗",
            "✓" if out else "", q[:40], " / ".join(path)))

    n = len(CASES)
    print("\n检索命中 %d/%d（%.0f%%），出处完整 %d/%d（%.0f%%）" % (
        hit_ok, n, 100 * hit_ok / n, cite_ok, n, 100 * cite_ok / n))

    if args.with_llm:
        print("\n--- LLM 烟测 ---")
        for q in ["调车作业计划如何编制？", "表格计算法的三个判别条件是什么？", "什么是调车钩？"]:
            r = qa.answer(q)
            ans = r["answer"]
            ok = (r["mode"] == "llm" and len(ans) > 40 and bool(re.search(r"\[\d+\]", ans)))
            print("%s %s | queries=%s | mode=%s | %s" % (
                "✓" if ok else "✗", q, r.get("queries"), r.get("mode"), ans[:80].replace("\n", " ")))

    return 0 if hit_ok / n >= 0.85 and cite_ok / n >= 0.95 else 1


if __name__ == "__main__":
    sys.exit(main())
