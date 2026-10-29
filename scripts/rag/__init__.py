# -*- coding: utf-8 -*-
"""教材 RAG：章节级 BM25 + bge-m3 向量 + 大模型组织答案。

用法：
    from scripts.rag import qa
    qa.answer("调车作业计划如何编制？")
"""

from .qa import answer, search, stats

__all__ = ["answer", "search", "stats"]
