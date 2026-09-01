"""检索语料：把两章教材原始 Markdown 按标题分节、按段落切成块，带出处元数据。"""

import os
import re

from rag import config

HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")

# 检索语料 = 教材原文（保证回答可溯源、忠实于教材）
SOURCES = [
    (
        "第四章 调车工作",
        os.path.join(
            config.PROJECT_ROOT, "assets", "铁路行车组织第2版-调车计划",
            "铁路行车组织第2版-调车计划.md",
        ),
    ),
    (
        "第十一章 技术站列车编组计划的编制",
        os.path.join(
            config.PROJECT_ROOT, "assets", "铁路行车组织第2版-技术站列车编组计划的编制",
            "铁路行车组织第2版-技术站列车编组计划的编制.md",
        ),
    ),
]

CHUNK_TARGET = 500  # 段落边界处达到该长度即切块
CHUNK_MAX = 900     # 无段落边界时的硬上限


def _split_into_chunks(text, source):
    chunks = []
    section = "概述"
    buf = []

    def flush():
        nonlocal buf
        if buf:
            body = "\n".join(buf).strip()
            if body:
                chunks.append({"source": source, "section": section, "text": body})
            buf = []

    for raw in text.splitlines():
        line = raw.rstrip()
        m = HEADING_RE.match(line)
        if m:
            flush()
            section = m.group(1).strip()
            continue
        if not line.strip():
            buf.append("")
            if sum(len(l) for l in buf) >= CHUNK_TARGET:
                flush()
            continue
        buf.append(line)
        if sum(len(l) for l in buf) >= CHUNK_MAX:
            flush()

    flush()
    return chunks


def load():
    """返回 [{id, source, section, text}, ...]。"""
    all_chunks = []
    cid = 0
    for source, path in SOURCES:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        for c in _split_into_chunks(text, source):
            c["id"] = cid
            cid += 1
            all_chunks.append(c)
    return all_chunks
