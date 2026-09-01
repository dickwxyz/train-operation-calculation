"""BM25 检索（纯 Python 实现），索引惰性构建、进程内缓存。"""

import math

from rag import corpus, tokenizer

K1 = 1.5
B = 0.75


class BM25Index:
    def __init__(self, chunks):
        self.chunks = chunks
        self.N = len(chunks)
        self.term_doc_freq = {}
        self.doc_term_tf = []
        self.doc_len = []
        for chunk in chunks:
            tf = {}
            for t in tokenizer.tokenize(chunk["text"]):
                tf[t] = tf.get(t, 0) + 1
            self.doc_term_tf.append(tf)
            self.doc_len.append(sum(tf.values()))
            for t in set(tf):
                self.term_doc_freq[t] = self.term_doc_freq.get(t, 0) + 1
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0

    def _idf(self, term):
        n = self.term_doc_freq.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def search(self, query, top_k=5):
        terms = list(dict.fromkeys(tokenizer.tokenize(query)))  # 去重
        if not terms or self.N == 0:
            return []
        scored = []
        for i, tf in enumerate(self.doc_term_tf):
            dl = self.doc_len[i]
            score = 0.0
            for t in terms:
                f = tf.get(t)
                if not f:
                    continue
                denom = f + K1 * (1 - B + B * dl / self.avgdl)
                score += self._idf(t) * (f * (K1 + 1)) / denom
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True, key=lambda x: x[0])
        results = []
        for score, i in scored[:top_k]:
            chunk = self.chunks[i]
            results.append({
                "score": round(score, 2),
                "source": chunk["source"],
                "section": chunk["section"],
                "snippet": chunk["text"],
            })
        return results


_index = None


def search(query, top_k=5):
    """进程内懒加载：首次调用构建索引。"""
    global _index
    if _index is None:
        _index = BM25Index(corpus.load())
    return _index.search(query, top_k)
