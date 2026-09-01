"""教材问答编排：检索相关片段 → 拼 prompt → DeepSeek 生成回答（未配置 key 时降级为仅返回原文）。"""

from rag import config, llm, retriever

_SYSTEM_PROMPT = (
    "你是《铁路行车组织（第2版）》课程的助教，专门回答铁路调车作业、列车编组计划相关问题。\n"
    "规则：\n"
    "1. 只依据下方提供的『教材片段』回答，不要编造教材中没有的内容；\n"
    "2. 每个要点尽量标注出处，如（第四章 调车工作）；\n"
    "3. 如果教材片段不足以回答，明确说明'教材相关章节未覆盖该内容'，并转述最相关的片段；\n"
    "4. 用简体中文回答，面向学生，简洁清楚。"
)

SNIPPET_LEN = 400  # 返回给前端的片段截断长度


def answer(question, top_k=5):
    hits = retriever.search(question, top_k)
    sources = [{
        "source": h["source"],
        "section": h["section"],
        "snippet": h["snippet"][:SNIPPET_LEN],
    } for h in hits]

    cfg = config.load()
    no_llm = not bool(cfg["api_key"])
    generated = None
    if not no_llm:
        try:
            generated = llm.chat(_build_messages(question, hits))
        except llm.LLMError:
            generated = None  # 调用失败：前端据 answer=null 降级展示原文

    return {
        "answer": generated,
        "no_llm": no_llm,
        "sources": sources,
    }


def _build_messages(question, hits):
    ctx = "\n\n".join(
        f"[{h['source']} / {h['section']}]\n{h['snippet']}" for h in hits
    )
    user = f"学生提问：{question}\n\n教材片段：\n{ctx}"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
