"""scripts — 调车作业计划（按站顺编组·调车表法）纯 Python 算法包。

依赖方向（单向，便于单测）:
parser → model → xialuo → tiaozheng → merges/tracks → simulator → objective
        → planner → shunting_plan
fixtures 依赖全部（仅测试用）。

`rag/` 是独立的教材原文检索问答包（不依赖上面的算法链，也不调用大模型）。
"""
