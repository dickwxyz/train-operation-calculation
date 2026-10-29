# -*- coding: utf-8 -*-
"""OpenAI 兼容的 LLM 客户端（纯 urllib，不依赖 requests/openai）。

`chat` 用 daemon 线程 + 队列做**总时长**超时：urllib 的 timeout 只管单次 socket 读，
模型流式慢返回时可能拖很久；这里保证调用方在 timeout 秒内一定拿到结果或 LLMError。
"""

from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.request

from . import config


class LLMError(RuntimeError):
    pass


def _request(url: str, api_key: str, payload: dict, timeout: int) -> str:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise LLMError("HTTP %s：%s" % (e.code, detail)) from e
    except urllib.error.URLError as e:
        raise LLMError("网络错误：%s" % e.reason) from e
    except (TimeoutError, OSError) as e:
        raise LLMError("请求超时/IO 错误：%s" % e) from e
    except json.JSONDecodeError as e:
        raise LLMError("响应不是合法 JSON：%s" % e) from e

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("响应缺少 choices[0].message.content：%s" % str(body)[:300])
    content = (content or "").strip()
    if not content:
        raise LLMError("模型返回空内容")
    return content


def chat(messages: list[dict], temperature: float | None = None,
         max_tokens: int | None = None, timeout: int | None = None) -> str:
    cfg = config.load_llm()
    if not cfg["api_key"]:
        raise LLMError("未配置 LLM_API_KEY（请在 .env 中设置）")
    timeout = timeout or config.LLM_TIMEOUT
    url = cfg["base_url"] + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": config.LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": config.LLM_MAX_TOKENS if max_tokens is None else max_tokens,
    }

    q: queue.Queue = queue.Queue(maxsize=1)

    def worker():
        try:
            q.put(("ok", _request(url, cfg["api_key"], payload, timeout)))
        except Exception as e:  # noqa: BLE001 - 原样带回主线程
            q.put(("err", e))

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    try:
        kind, value = q.get(timeout=timeout + 2)
    except queue.Empty:
        raise LLMError("大模型请求超时（>%s 秒）" % timeout)
    if kind == "err":
        if isinstance(value, LLMError):
            raise value
        raise LLMError("%s: %s" % (type(value).__name__, value))
    return value
