# -*- coding: utf-8 -*-
"""numpy 内存向量后端：读取 rag_index/，对 parent section 做向量打分。

不依赖向量数据库；1594×1024 的矩阵只有约 6.5MB。
以后要换 Chroma/faiss/API embedding，只需实现同样的接口。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import numpy as np

from . import config


class VectorIndexError(RuntimeError):
    pass


class VectorBackend(Protocol):
    available: bool

    def search_parent_scores(self, queries: list[str]) -> list[dict[str, float]]:
        """每条 query 返回 {parent_key: 相似度}。"""

    def chunk_scores(self, query: str) -> dict[str, float]:
        """返回 {chunk_id: 余弦相似度}，用于 parent 内 child 排序。"""


class NullVectorBackend:
    available = False

    def search_parent_scores(self, queries: list[str]) -> list[dict[str, float]]:
        return [{} for _ in queries]

    def chunk_scores(self, query: str) -> dict[str, float]:
        return {}


class NumpyVectorBackend:
    def __init__(self, index_dir: Path | None = None, embedder=None):
        self.index_dir = Path(index_dir or config.INDEX_DIR)
        self._embedder = embedder
        self.available = False
        self.meta: dict = {}
        self.parents: list[dict] = []
        self.chunks: list[dict] = []
        self.embeddings: np.ndarray | None = None
        self._parent_rows: dict[str, list[int]] = {}
        self._load()

    def _load(self) -> None:
        meta_path = self.index_dir / "meta.json"
        emb_path = self.index_dir / "chunk_embeddings.npy"
        chunks_path = self.index_dir / "chunks.jsonl"
        parents_path = self.index_dir / "parents.json"
        if not all(p.is_file() for p in (meta_path, emb_path, chunks_path, parents_path)):
            self.available = False
            return
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.embeddings = np.load(emb_path).astype(np.float32)
        self.chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.parents = json.loads(parents_path.read_text(encoding="utf-8"))
        for i, c in enumerate(self.chunks):
            self._parent_rows.setdefault(c["parent_key"], []).append(i)
        self.available = self.embeddings is not None and len(self.chunks) == len(self.embeddings)

    def _get_embedder(self):
        if self._embedder is None:
            from .embedding import BgeM3Embedder
            self._embedder = BgeM3Embedder()
        return self._embedder

    def _encode(self, queries: list[str]) -> np.ndarray:
        if not self.available:
            raise VectorIndexError("向量索引不可用，请先运行 python -m scripts.rag.build_index")
        return self._get_embedder().encode(queries)

    def search_parent_scores(self, queries: list[str]) -> list[dict[str, float]]:
        if not self.available:
            return [{} for _ in queries]
        q = self._encode(queries)
        sims = self.embeddings @ q.T  # [N, Q]
        out: list[dict[str, float]] = []
        for qi in range(len(queries)):
            scores: dict[str, float] = {}
            for parent_key, rows in self._parent_rows.items():
                if not rows:
                    continue
                vals = sims[rows, qi]
                # parent 分取该节最相关 chunk 的余弦；再叠加前 3 名的均值
                top = np.sort(vals)[-3:]
                scores[parent_key] = float(0.7 * vals.max() + 0.3 * top.mean())
            out.append(scores)
        return out

    def chunk_scores(self, query: str) -> dict[str, float]:
        if not self.available:
            return {}
        q = self._encode([query])[0]
        sims = self.embeddings @ q
        return {c["id"]: float(sims[i]) for i, c in enumerate(self.chunks)}
