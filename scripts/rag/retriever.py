# -*- coding: utf-8 -*-
"""章节级混合检索：词/字 BM25 + bge-m3 向量，按 parent section 做 RRF 融合。

不按题型写正则；检索只看「哪些章节最相关」，题型判断与答案组织交给 LLM。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import config
from .corpus import Chunk, Parent, build_parents, load_chunks, normalize_for_index

try:
    import jieba
    import logging as _logging

    jieba.setLogLevel(_logging.ERROR)
    for _w in config.DOMAIN_WORDS:
        jieba.add_word(_w)
    _HAS_JIEBA = True
except Exception:  # pragma: no cover
    _HAS_JIEBA = False

_ASCII_RE = re.compile(r"[a-zA-Z0-9]+")
_STRUCT_RE = re.compile(r"步骤|第\s*[一二三四五六七八九十\d]+\s*步|包括|分为|小结")
_DEF_RE = re.compile(r"称为|是指|所谓|叫做|定义为|的含义是")


def _fallback_words(text: str) -> list[str]:
    tokens = [m.group(0).lower() for m in _ASCII_RE.finditer(text)]
    for run in re.findall(r"[一-鿿]+", text):
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def tokenize_words(text: str) -> list[str]:
    s = normalize_for_index(text)
    if _HAS_JIEBA:
        out = []
        for w in jieba.cut(s, cut_all=False):
            w = w.strip()
            if not w or re.fullmatch(r"[\W_]+", w):
                continue
            if len(w) == 1 and re.fullmatch(r"[一-鿿]", w):
                continue
            if w in config.STOPWORDS:
                continue
            out.append(w)
        return out or _fallback_words(s)
    return [w for w in _fallback_words(s) if w not in config.STOPWORDS]


def tokenize_chars(text: str) -> list[str]:
    s = re.sub(r"\s+", "", normalize_for_index(text))
    return [s[i:i + 2] for i in range(max(0, len(s) - 1))]


class BM25Index:
    def __init__(self, texts: list[str], tokenizer=tokenize_words):
        self.docs = [tokenizer(t) for t in texts]
        self.doc_len = [len(d) for d in self.docs]
        self.n = len(self.docs)
        self.avgdl = sum(self.doc_len) / max(1, self.n)
        self.tf: list[dict[str, int]] = []
        self.df: dict[str, int] = {}
        for doc in self.docs:
            counts: dict[str, int] = {}
            for t in doc:
                counts[t] = counts.get(t, 0) + 1
            self.tf.append(counts)
            for t in counts:
                self.df[t] = self.df.get(t, 0) + 1

    def idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log(1 + (self.n - n + 0.5) / (n + 0.5))

    def scores(self, tokens: list[str]) -> list[float]:
        out = [0.0] * self.n
        for t in set(tokens):
            if t not in self.df:
                continue
            idf = self.idf(t)
            for i, counts in enumerate(self.tf):
                f = counts.get(t)
                if not f:
                    continue
                dl = self.doc_len[i] or 1
                denom = f + config.BM25_K1 * (1 - config.BM25_B + config.BM25_B * dl / (self.avgdl or 1))
                out[i] += idf * f * (config.BM25_K1 + 1) / denom
        return out


def _rank_map(scores: dict[str, float]) -> dict[str, int]:
    order = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return {k: i + 1 for i, (k, _) in enumerate(order)}


def _rrf(rank_maps: list[tuple[dict[str, int], int]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ranks, k in rank_maps:
        for key, rank in ranks.items():
            out[key] = out.get(key, 0.0) + 1.0 / (k + rank)
    return out


@dataclass
class ParentHit:
    parent: Parent
    score: float
    chunks: list[Chunk] = field(default_factory=list)


@dataclass
class RetrievalResult:
    parents: list[ParentHit]
    queries: list[str]
    vector_available: bool = False


class _Indices:
    def __init__(self):
        self.chunks, self.stats = load_chunks()
        self.parents = build_parents(self.chunks)
        self.parent_by_key = {p.key: p for p in self.parents}
        self.chunk_by_id = {c.id: c for c in self.chunks}
        self.chunk_words = BM25Index([c.index_text for c in self.chunks], tokenize_words)
        self.chunk_chars = BM25Index([c.index_text for c in self.chunks], tokenize_chars)
        self.chunk_pos = {c.id: i for i, c in enumerate(self.chunks)}


_INDICES: _Indices | None = None


def get_indices() -> _Indices:
    global _INDICES
    if _INDICES is None:
        _INDICES = _Indices()
    return _INDICES


def stats() -> dict:
    idx = get_indices()
    return {
        "chunks": len(idx.chunks),
        "parents": len(idx.parents),
        **idx.stats,
    }


def _parent_query_scores(idx: _Indices, query: str, vector_backend) -> dict[str, float]:
    """单条 query：chunk 级 BM25（词/字）聚合到 parent + 向量，RRF 融合。"""
    w = idx.chunk_words.scores(tokenize_words(query))
    c = idx.chunk_chars.scores(tokenize_chars(query))
    word_scores: dict[str, float] = {}
    char_scores: dict[str, float] = {}
    for p in idx.parents:
        rows = [idx.chunk_pos[cid] for cid in p.chunk_ids if cid in idx.chunk_pos]
        if not rows:
            continue
        wv = sorted((w[i] for i in rows), reverse=True)
        cv = sorted((c[i] for i in rows), reverse=True)
        word_scores[p.key] = wv[0] + 0.3 * (sum(wv[:3]) / len(wv[:3]))
        char_scores[p.key] = cv[0] + 0.3 * (sum(cv[:3]) / len(cv[:3]))

    vec: dict[str, float] = {}
    if vector_backend is not None and getattr(vector_backend, "available", False):
        vec = vector_backend.search_parent_scores([query])[0]

    # 相关性闸门：词面完全无命中时，只有足够强的向量相似才保留（挡住“今天天气”类问题）
    word_max = max(list(word_scores.values()) + [0.0])
    vector_max = max(list(vec.values()) + [0.0])
    if word_max <= config.MIN_BM25_SCORE and vector_max < config.MIN_VECTOR_ONLY:
        return {}

    fused = _rrf([
        (_rank_map(word_scores), config.RRF_K_BM25),
        (_rank_map(char_scores), config.RRF_K_BM25 + 10),
    ])
    if vec:
        fused = _rrf([
            (_rank_map(fused), config.RRF_K_BM25),
            (_rank_map(vec), config.RRF_K_VEC),
        ])

    # 标题命中：查询词出现在任一级标题中，按层级加一点分
    q_terms = set(tokenize_words(query))
    for p in idx.parents:
        hit_levels = sum(1 for level in p.heading_path if q_terms and any(t in level for t in q_terms))
        if hit_levels:
            fused[p.key] = fused.get(p.key, 0.0) * (1 + config.HEADING_BOOST * hit_levels)
    return fused


def search(question: str | list[str], vector_backend=None,
           top_parents: int | None = None) -> RetrievalResult:
    """检索并选出每个 parent 内的候选 chunks。"""
    idx = get_indices()
    queries = [question] if isinstance(question, str) else [q for q in question if q.strip()]
    if not queries:
        return RetrievalResult([], [], False)

    per_query = [_parent_query_scores(idx, q, vector_backend) for q in queries]
    # 多查询再做一次 RRF
    fused = _rrf([(_rank_map(s), config.RRF_K_QUERY) for s in per_query])

    # parent 内 child 排序：词/字 BM25 + 向量 + 结构优先级
    chunk_word = idx.chunk_words.scores(tokenize_words(" ".join(queries)))
    chunk_char = idx.chunk_chars.scores(tokenize_chars(" ".join(queries)))
    word_map = {c.id: chunk_word[i] for i, c in enumerate(idx.chunks)}
    char_map = {c.id: chunk_char[i] for i, c in enumerate(idx.chunks)}
    vec_map: dict[str, float] = {}
    if vector_backend is not None and getattr(vector_backend, "available", False):
        for q in queries:
            for cid, s in vector_backend.chunk_scores(q).items():
                vec_map[cid] = max(vec_map.get(cid, -1.0), s)

    rank_maps = [(_rank_map(word_map), config.RRF_K_BM25),
                 (_rank_map(char_map), config.RRF_K_BM25 + 10)]
    if vec_map:
        rank_maps.append((_rank_map(vec_map), config.RRF_K_VEC))
    chunk_fused = _rrf(rank_maps)

    order = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    picked: list[ParentHit] = []
    for key, score in order[:top_parents or config.TOP_PARENTS]:
        parent = idx.parent_by_key.get(key)
        if parent is None:
            continue
        candidates = []
        for cid in parent.chunk_ids:
            c = idx.chunk_by_id.get(cid)
            if c is None:
                continue
            s = chunk_fused.get(cid, 0.0)
            if _STRUCT_RE.search(c.text):
                s *= config.STRUCTURE_BOOST
            if _DEF_RE.search(c.text):
                s *= config.STRUCTURE_BOOST
            candidates.append((s, c))
        # 结构块/例题优先；选到预算后再按原文顺序排
        candidates.sort(key=lambda x: x[0], reverse=True)
        chosen: list[Chunk] = []
        used = 0
        for _, c in candidates:
            if used + len(c.text) > config.PARENT_CHUNK_BUDGET and chosen:
                continue
            chosen.append(c)
            used += len(c.text)
            if used >= config.PARENT_CHUNK_BUDGET:
                break
        # 同一例题的其它块尽量补齐
        ex_ids = {c.example_id for c in chosen if c.example_id}
        if ex_ids:
            for cid in parent.chunk_ids:
                c = idx.chunk_by_id.get(cid)
                if c and c.example_id in ex_ids and c not in chosen and used + len(c.text) <= config.PARENT_CHUNK_BUDGET:
                    chosen.append(c)
                    used += len(c.text)
        chosen.sort(key=lambda c: idx.chunk_pos[c.id])
        picked.append(ParentHit(parent=parent, score=round(score, 6), chunks=chosen))

    return RetrievalResult(
        parents=picked, queries=queries,
        vector_available=bool(vector_backend is not None and getattr(vector_backend, "available", False)),
    )
