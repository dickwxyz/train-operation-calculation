# -*- coding: utf-8 -*-
"""RAG 门面：查询改写 → 章节级混合检索 → 大模型组织答案。"""

from __future__ import annotations

import re

from . import config, llm, retriever
from .corpus import display_text
from .embedding import EmbeddingError
from .vector import NumpyVectorBackend, VectorIndexError

_SYSTEM = """你是《铁路行车组织》课程助教。只能使用用户消息中给出的教材片段回答，严禁使用片段之外的任何知识。
1. 第一行只输出【题型】选择/填空/简答/名词解释/方法步骤/计算，不要写“题型判断：”。
2. 方法步骤题：先完整列出教材的步骤。若片段有“步骤为：……”或“第1步…第2步…”的总结，必须严格按其次序和数量列出，不得合并、增补或遗漏；每步保留教材术语，并用 1–3 句片段原句说明“怎么做/为什么”。不要先写编制原则、计划形式、背景等与步骤无关的内容，也不要追加“补充要点”。
3. 简答题：分条列出教材要点，每条 1–2 句原文依据。
4. 名词解释：给出教材定义句；填空：给出原文术语；选择：只在原文明确支持时判断，否则说明不足。
5. 计算题：写出教材公式与例题步骤；不编造题目数值答案。
6. 每个要点后用 [编号] 标注来源；片段不足时明确说“教材原文未直接给出”，不得猜测。
7. 只回答与问题直接相关的内容；输出纯文本，不要 Markdown 标记（不要 **、#、-），用 1. 2. 3. 和换行。"""

_REWRITE = """你是铁路行车组织课程的检索助手。把学生的问题改写成 2–4 条教材式检索词/短句：
1. 使用教材术语（如 调车作业计划、下落、调整、暂合列、钩计划、绝对条件、通过能力）；
2. 保留原问题中的专有名词、数字、公式符号；
3. 不要回答问题、不要解释；每行一条，最多 4 条，尽量短。
学生问题：%s"""

_VECTOR: NumpyVectorBackend | None = None

# 领域门槛：问题里至少要出现一个课程相关词，避免把“今天天气”改写成教材检索式
_DOMAIN_RE = re.compile(r"例\s*\d+\.\d+|第[一二三四五六七八九十百零〇\d]+[章节篇]")
_DOMAIN_HINTS = (
    "调车", "编组", "列车", "车站", "运行图", "通过能力", "集结", "取送",
    "直达", "车流", "机车", "股道", "驼峰", "计划", "作业", "车",
)


def _has_domain(question: str) -> bool:
    if _DOMAIN_RE.search(question):
        return True
    if any(w in question for w in config.DOMAIN_WORDS if len(w) >= 2):
        return True
    return any(h in question for h in _DOMAIN_HINTS)


def _vector() -> NumpyVectorBackend:
    global _VECTOR
    if _VECTOR is None:
        _VECTOR = NumpyVectorBackend()
    return _VECTOR


def _page_label(chunks) -> str:
    pages = [(c.page_start, c.page_end, c.page_conf) for c in chunks if c.page_start]
    if not pages:
        return "页码未标注"
    start = min(p[0] for p in pages)
    end = max(p[1] or p[0] for p in pages)
    conf = "range" if any(p[2] == "range" for p in pages) else "exact"
    s = "印刷页 %03d" % start if start == end else "印刷页 %03d–%03d" % (start, end)
    return s + ("（补自）" if conf == "range" else "")


def rewrite_queries(question: str) -> list[str]:
    """LLM 把口语问题改写成 2–4 条教材式检索式；失败则只用原问题。"""
    q = question.strip()
    if not config.QUERY_REWRITE:
        return [q]
    try:
        text = llm.chat(
            [{"role": "user", "content": _REWRITE % q}],
            temperature=0.0, max_tokens=config.QUERY_REWRITE_MAX_TOKENS,
            timeout=config.QUERY_REWRITE_TIMEOUT,
        )
    except llm.LLMError:
        return [q]
    out: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.、)])\s*", "", line).strip()
        line = line.strip("“”\"'` ")
        if 2 <= len(line) <= 80 and line not in out:
            out.append(line)
    out = out[:config.QUERY_REWRITE_MAX]
    if q not in out:
        out.insert(0, q)
    return out or [q]


def _context(result: retriever.RetrievalResult):
    blocks, sources = [], []
    used = 0
    for n, hit in enumerate(result.parents, 1):
        text_parts = []
        for c in hit.chunks:
            t = display_text(c.text)
            if used + len(t) > config.MAX_CONTEXT_CHARS and blocks:
                break
            text_parts.append(t)
            used += len(t)
        if not text_parts:
            continue
        head = " / ".join(hit.parent.heading_path)
        page = _page_label(hit.chunks)
        blocks.append("[%d] %s（%s）\n%s" % (n, head, page, "\n".join(text_parts)))
        snippet = display_text(hit.parent.text)[:400]
        sources.append({
            "n": n, "source": hit.parent.chapter,
            "section": hit.parent.section or "（未分节）",
            "printed_page": page, "block_type": "section",
            "score": hit.score, "snippet": snippet,
        })
        if used >= config.MAX_CONTEXT_CHARS:
            break
    return "\n\n".join(blocks), sources


def answer(question: str) -> dict:
    question = (question or "").strip()
    if not question:
        return {"answer": "问题不能为空。", "sources": [], "qtype": "综合",
                "mode": "llm_error", "no_llm": False, "queries": []}

    if not _has_domain(question):
        return {
            "answer": "教材中没有找到与该问题直接相关的内容，请换用课程术语提问。",
            "sources": [], "qtype": "综合", "mode": "no_result",
            "no_llm": False, "queries": [],
        }

    backend = _vector()
    if not backend.available:
        return {
            "answer": "向量索引不可用。请先运行：venv/bin/python -m scripts.rag.build_index",
            "sources": [], "qtype": "综合", "mode": "index_error",
            "no_llm": True, "queries": [],
        }

    queries = rewrite_queries(question)
    try:
        result = retriever.search(queries, vector_backend=backend)
    except (VectorIndexError, EmbeddingError) as e:
        return {
            "answer": "向量检索失败：%s" % e, "sources": [], "qtype": "综合",
            "mode": "index_error", "no_llm": True, "queries": queries,
        }

    context, sources = _context(result)
    if not context:
        return {
            "answer": "教材中没有找到与该问题直接相关的内容，请换用课程术语提问。",
            "sources": [], "qtype": "综合", "mode": "no_result",
            "no_llm": False, "queries": queries,
        }

    user = "【教材片段】\n%s\n\n【问题】%s" % (context, question)
    try:
        text = llm.chat([{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": user}])
    except llm.LLMError as e:
        return {
            "answer": "大模型调用失败：%s" % e, "sources": sources, "qtype": "综合",
            "mode": "llm_error", "no_llm": False, "queries": queries,
        }

    m = re.search(r"【题型】\s*([^\n]+)", text) or re.search(r"题型判断[:：]\s*([^\n。]+)", text)
    qtype = m.group(1).strip() if m else "综合"
    return {
        "answer": text, "sources": sources, "qtype": qtype,
        "mode": "llm", "no_llm": False, "queries": queries,
    }


def search(question: str, top_parents: int | None = None) -> list[dict]:
    """调试：返回章节级命中与候选 chunk。"""
    result = retriever.search(question, vector_backend=_vector(),
                              top_parents=top_parents or config.TOP_PARENTS)
    out = []
    for hit in result.parents:
        out.append({
            "chapter": hit.parent.chapter,
            "section": hit.parent.section,
            "heading_path": hit.parent.heading_path,
            "score": hit.score,
            "printed_page": _page_label(hit.chunks),
            "chunks": [
                {"id": c.id, "block_type": c.block_type,
                 "text": display_text(c.text)[:300]}
                for c in hit.chunks
            ],
        })
    return out


def stats() -> dict:
    s = retriever.stats()
    s["vector_available"] = _vector().available
    s["index_dir"] = str(config.INDEX_DIR)
    return s
