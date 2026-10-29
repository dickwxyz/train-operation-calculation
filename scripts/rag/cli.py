# -*- coding: utf-8 -*-
"""命令行入口：章节级混合检索 + 大模型整理答案。

用法：
    venv/bin/python -m scripts.rag "什么是调车钩？"
    venv/bin/python -m scripts.rag.cli "F节怎么算" --json
    venv/bin/python -m scripts.rag.cli --stats
    venv/bin/python -m scripts.rag.cli "调车" --search
"""

from __future__ import annotations

import argparse
import json
import sys

from . import qa


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="教材 RAG：章节级 BM25 + bge-m3 + 大模型")
    ap.add_argument("question", nargs="*", help="要提问的问题")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--search", action="store_true", help="只显示章节级检索命中，不调用大模型")
    ap.add_argument("--top-parents", type=int, default=None, help="显示/检索的章节数")
    ap.add_argument("--stats", action="store_true", help="显示索引统计后退出")
    args = ap.parse_args(argv)

    if args.stats:
        print(json.dumps(qa.stats(), ensure_ascii=False, indent=2))
        return 0

    question = " ".join(args.question).strip()
    if not question:
        ap.print_help()
        return 2

    if args.search:
        rows = qa.search(question, top_parents=args.top_parents)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for i, r in enumerate(rows, 1):
                print("%d. [%.4f] %s · %s" % (
                    i, r["score"], " / ".join(r["heading_path"]), r["printed_page"]))
                for c in r["chunks"]:
                    print("   - [%s] %s" % (c["block_type"], c["text"].replace("\n", " ")[:140]))
        return 0

    result = qa.answer(question)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if result.get("queries"):
        print("检索式：" + " | ".join(result["queries"]))
        print()
    print(result["answer"])
    if result.get("sources"):
        print("\n--- 教材出处 ---")
        for s in result["sources"]:
            print("[%d] %s / %s · %s" % (
                s.get("n", 0), s["source"], s["section"], s["printed_page"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
