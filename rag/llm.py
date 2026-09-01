"""OpenAI 兼容 chat 客户端（urllib，零依赖），默认对接 DeepSeek v4 Flash。"""

import json
import urllib.error
import urllib.request

from rag import config


class LLMError(Exception):
    pass


def chat(messages, temperature=0.2, timeout=60):
    """调用 {base_url}/chat/completions，返回助手消息文本。"""
    cfg = config.load()
    if not cfg["api_key"]:
        raise LLMError("LLM_API_KEY 未配置")

    url = cfg["base_url"] + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg["api_key"],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise LLMError(f"LLM HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"LLM 网络错误: {e.reason}") from e

    try:
        return body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"LLM 响应格式异常: {str(body)[:300]}") from e
