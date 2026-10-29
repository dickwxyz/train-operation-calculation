# -*- coding: utf-8 -*-
"""构建 031 根目录 rag_index/：chunks、parent sections、bge-m3 embeddings。

    venv/bin/python -m scripts.rag.build_index            # 已是最新则跳过
    venv/bin/python -m scripts.rag.build_index --rebuild  # 强制重建

生成文件：
    rag_index/chunks.jsonl
    rag_index/chunk_embeddings.npy
    rag_index/parents.json
    rag_index/meta.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config
from .corpus import build_parents, load_chunks
from .embedding import BgeM3Embedder, EmbeddingError


def corpus_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def is_current(meta_path: Path, sha: str, chunks: int, dim: int) -> bool:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        meta.get("corpus_sha1") == sha
        and meta.get("chunk_count") == chunks
        and meta.get("dim") == dim
        and meta.get("model") == "bge-m3"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="构建教材 RAG 向量索引")
    ap.add_argument("--rebuild", action="store_true", help="忽略已有索引，强制重建")
    ap.add_argument("--batch-size", type=int, default=config.EMBEDDING_BATCH)
    ap.add_argument("--limit", type=int, default=0, help="只编码前 N 个 chunk（调试用）")
    args = ap.parse_args()

    if not config.CORPUS_PATH.is_file():
        sys.exit("语料不存在：%s" % config.CORPUS_PATH)
    embedder = BgeM3Embedder()
    if not embedder.available():
        sys.exit("缺少 bge-m3 模型：%s 或 %s" % (config.BGE_ONNX, config.BGE_TOKENIZER))

    chunks, stats = load_chunks()
    parents = build_parents(chunks)
    sha = corpus_sha1(config.CORPUS_PATH)
    meta_path = config.INDEX_DIR / "meta.json"
    if not args.rebuild and not args.limit and is_current(
            meta_path, sha, len(chunks), config.EMBEDDING_DIM):
        print("索引已是最新：%s（%d chunks）" % (config.INDEX_DIR, len(chunks)))
        return 0

    use = chunks[:args.limit] if args.limit else chunks
    print("语料：%s" % config.CORPUS_PATH)
    print("chunks：%d；parents：%d；开始 bge-m3 编码…" % (len(use), len(parents)))
    t0 = time.time()
    texts = ["\n".join(c.heading_path) + "\n" + c.text for c in use]
    try:
        embeddings = embedder.encode(texts, batch_size=args.batch_size, progress=True)
    except EmbeddingError as e:
        sys.exit(str(e))
    elapsed = time.time() - t0

    tmp = config.INDEX_DIR.with_name(config.INDEX_DIR.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    with open(tmp / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in use:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    np.save(tmp / "chunk_embeddings.npy", embeddings.astype(np.float32))
    (tmp / "parents.json").write_text(
        json.dumps([p.__dict__ for p in parents], ensure_ascii=False, indent=1),
        encoding="utf-8")
    meta = {
        "corpus": str(config.CORPUS_PATH),
        "corpus_sha1": sha,
        "chunk_count": len(use),
        "parent_count": len(parents),
        "model": "bge-m3",
        "model_path": str(config.BGE_DIR),
        "dim": int(embeddings.shape[1]) if len(embeddings) else config.EMBEDDING_DIM,
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": round(elapsed, 1),
        "limit": args.limit or None,
    }
    (tmp / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if config.INDEX_DIR.exists():
        shutil.rmtree(config.INDEX_DIR)
    os.replace(tmp, config.INDEX_DIR)
    print("完成：%s（%d 个向量，%.1f 秒）" % (config.INDEX_DIR, len(embeddings), elapsed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
