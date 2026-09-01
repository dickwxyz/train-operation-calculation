"""LLM 配置：环境变量优先，其次项目根目录 .env，最后内置默认值（DeepSeek）。"""

import os

# rag/ 的上一级即项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

DEFAULTS = {
    "LLM_BASE_URL": "https://api.deepseek.com/v1",
    "LLM_API_KEY": "",
    "LLM_MODEL": "deepseek-v4-flash",
}


def _parse_env_file(path):
    """极简 .env 解析：逐行 KEY=VALUE，忽略空行与 # 注释，允许行首 export。"""
    values = {}
    if not os.path.isfile(path):
        return values
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    values[key] = val
    except OSError:
        pass
    return values


def load():
    """返回 {base_url, api_key, model}。优先级：环境变量 > .env > 默认值。"""
    file_values = _parse_env_file(ENV_PATH)
    out = {
        "base_url": (os.environ.get("LLM_BASE_URL") or file_values.get("LLM_BASE_URL") or DEFAULTS["LLM_BASE_URL"]),
        "api_key": (os.environ.get("LLM_API_KEY") or file_values.get("LLM_API_KEY") or DEFAULTS["LLM_API_KEY"]),
        "model": (os.environ.get("LLM_MODEL") or file_values.get("LLM_MODEL") or DEFAULTS["LLM_MODEL"]),
    }
    out["base_url"] = out["base_url"].rstrip("/")
    return out
