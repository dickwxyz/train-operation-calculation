# -*- coding: utf-8 -*-
"""bge-m3 ONNX 编码器（与 034 项目相同的本地模型，不依赖 transformers/torch）。

模型输出第二个张量 `sentence_embedding` 已是 1024 维归一化向量，直接使用；
tokenizer 用 tokenizers 直接读 `bge-m3/tokenizer.json`。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import config

_PAD_ID = 1  # bge-m3/XLM-R pad token id


class EmbeddingError(RuntimeError):
    pass


class BgeM3Embedder:
    def __init__(self, model_dir: Path | None = None, max_length: int | None = None):
        self.model_dir = Path(model_dir or config.BGE_DIR)
        self.onnx_path = self.model_dir / "onnx" / "model.onnx"
        self.tokenizer_path = self.model_dir / "tokenizer.json"
        self.max_length = max_length or config.EMBEDDING_MAX_LENGTH
        self._session = None
        self._tokenizer = None

    def available(self) -> bool:
        return self.onnx_path.is_file() and self.tokenizer_path.is_file()

    def _load(self) -> None:
        if self._session is not None:
            return
        if not self.available():
            raise EmbeddingError(
                "未找到 bge-m3 模型：%s / %s" % (self.onnx_path, self.tokenizer_path))
        import onnxruntime
        from tokenizers import Tokenizer

        self._session = onnxruntime.InferenceSession(
            str(self.onnx_path), providers=["CPUExecutionProvider"])
        tok = Tokenizer.from_file(str(self.tokenizer_path))
        tok.enable_truncation(max_length=self.max_length)
        tok.enable_padding(pad_id=_PAD_ID, pad_token="<pad>")
        self._tokenizer = tok

    def encode(self, texts: list[str], batch_size: int | None = None,
               progress: bool = False) -> np.ndarray:
        """返回 [N, 1024] float32，已 L2 归一化。"""
        self._load()
        assert self._session is not None and self._tokenizer is not None
        batch_size = batch_size or config.EMBEDDING_BATCH
        out: list[np.ndarray] = []
        total = len(texts)
        for start in range(0, total, batch_size):
            batch = [t[:4000] for t in texts[start:start + batch_size]]
            enc = self._tokenizer.encode_batch(batch)
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            outputs = self._session.run(None, {"input_ids": ids, "attention_mask": mask})
            # 输出顺序：token_embeddings, sentence_embedding
            emb = np.asarray(outputs[1], dtype=np.float32)
            emb = emb / np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-9, None)
            out.append(emb)
            if progress:
                print("  embedding %d/%d" % (min(start + batch_size, total), total), flush=True)
        if not out:
            return np.zeros((0, config.EMBEDDING_DIM), dtype=np.float32)
        return np.vstack(out)
