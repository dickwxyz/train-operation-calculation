"""中文分词：可用时用 jieba，否则回退到按标点切分 + 字符二元组（零依赖）。"""

import re

_HAS_JIEBA = None
_SPLIT_RE = re.compile(r"[\s\W_]+", flags=re.UNICODE)
_ASCII_WORD_RE = re.compile(r"^[a-z0-9]+$")


def _has_jieba():
    global _HAS_JIEBA
    if _HAS_JIEBA is None:
        try:
            import jieba  # noqa: F401
            _HAS_JIEBA = True
        except ImportError:
            _HAS_JIEBA = False
    return _HAS_JIEBA


def _fallback_tokens(text):
    """按标点/空白切分；ASCII 词保留整词，中文片段产出整段 + 相邻字符二元组。"""
    toks = []
    for seg in _SPLIT_RE.split(text):
        if not seg:
            continue
        if _ASCII_WORD_RE.match(seg):
            toks.append(seg)
        else:
            toks.append(seg)
            for i in range(len(seg) - 1):
                toks.append(seg[i:i + 2])
    return toks


def tokenize(text):
    text = text.lower()
    if _has_jieba():
        import jieba
        return [t for t in jieba.cut(text) if t.strip()]
    return _fallback_tokens(text)
