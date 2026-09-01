# 调车作业计划智能体

铁路**调车作业计划**教学演示 Web 应用：输入到达列车、分类股道数和目标编组顺序，用**分组选编法**自动生成调车作业计划表；并内置基于《铁路行车组织（第2版）》教材的**检索问答**功能。

面向学校局域网内多名学生并发使用，求解为毫秒级计算，`threaded` 开发服务器即可支撑。

## 功能特性

- **调车作业计划生成**：输入车辆（车号+去向）、股道数、目标编组顺序，输出分钩作业计划表（解体/编组/牵出各钩的作业股道、摘挂、辆数、车号、说明）与最终出发编成，各阶段着色区分。
- **教材问答**：基于教材第四、十一章原文，BM25 检索相关片段 + DeepSeek 生成带出处的回答；未配置 API Key 时自动降级为仅展示教材原文片段。
- **教材知识库**：`knowledge_base/` 提供结构化提炼（章节梳理、术语表、算法与代码对照、算例集），供教学与算法改进参考。
- 零第三方依赖扩展（新增仅 `jieba`），纯 Python 实现检索。

## 快速开始

前置要求：Python 3.9+（推荐 3.12）。

```bash
# 1. 创建虚拟环境并安装依赖
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 2. 启动服务（监听 0.0.0.0:50000）
venv/bin/python app.py

# 3. 浏览器访问
# http://<服务器IP>:50000
```

端口固定为 **50000**（避开 macOS AirPlay 接收器占用的 5000）。

## 使用说明

### 调车作业计划

1. 设置**目标编组顺序**（如 `甲 乙 丙`）与**分类股道数**（2~6）。
2. 填写**车辆列表**：车号 + 去向，从机车端到尾部排列（表格**最下方一行是机车端**）。
3. 点击「计算调车计划」，查看分钩计划表与最终编成。

### 教材问答

访问 `/qa`，输入问题（如「什么是调车钩？」），获得基于教材原文的生成式回答及出处片段。

## 配置（.env）

复制 `.env.example` 为 `.env` 并填写，即可启用生成式问答：

```bash
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-你的key
LLM_MODEL=deepseek-v4-flash
```

- 接口为 **OpenAI 兼容**，修改 `LLM_BASE_URL` / `LLM_MODEL` 可切换其他服务（Ollama、智谱、通义等）。
- **未填写 `LLM_API_KEY`** 时，问答功能降级为「仅展示检索到的教材原文片段」，其余功能不受影响。
- `.env` 含密钥，已加入 `.gitignore`，不会上传。

## API

### `POST /api/solve` — 生成调车作业计划

```json
{
  "cars": [{"id": "H", "dest": "乙"}, {"id": "G", "dest": "丙"}],
  "num_tracks": 3,
  "target_order": ["甲", "乙", "丙"]
}
```

返回 `{success, steps[], final_formation[], stats{total_steps, pull_out_count, break_up_count, make_up_count, tracks_used}}`。

### `POST /api/qa` — 教材问答

```json
{ "question": "什么是调车钩？" }
```

返回 `{success, answer, no_llm, sources[{source, section, snippet}]}`；`no_llm:true` 或 `answer:null` 表示大模型未配置/调用失败。

## 项目结构

```
app.py                  # Flask 入口（/、/qa、/api/solve、/api/qa）
scripts/shunting_plan.py # 分组选编法求解器（纯算法）
rag/                    # 教材问答后端：corpus(分块)/tokenizer(分词)/retriever(BM25)/llm(DeepSeek)/config(.env)
knowledge_base/         # 教材知识库（章节梳理、术语表、算法与代码对照、算例集）
static/                 # 前端：index.html(求解页)、qa.html(问答页)、style.css
assets/                 # 教材原始 PDF 与章节摘录（检索语料，未纳入版本控制）
```

## 教材问答原理

1. `rag/corpus.py` 把教材第四、十一章原文按标题分块（带章节出处）。
2. 收到问题后，`rag/retriever.py` 用 **BM25** 检索最相关的 5 段原文。
3. `rag/qa.py` 把问题 + 原文片段拼入提示词，交给 DeepSeek 生成回答（要求标注出处、不编造教材内容）。

## 说明

- **`assets/` 未纳入版本控制**（教材有版权、体积大）。问答的检索语料来自该目录，从 Git 克隆后需自行补充教材章节 Markdown 到 `assets/`（目录结构见 `rag/corpus.py` 的 `SOURCES`），否则问答仅返回空结果。
- 求解器 `scripts/shunting_plan.py` 实现的是教材「分组选编法」的简化子集；与完整「调车表法」（下落/调整/合并）的差异与改进方向见 `knowledge_base/算法方法与代码对照.md`。
- 本项目为教学演示，使用 Flask 开发服务器即可；生产部署请换用 WSGI 服务器并关闭 `debug`。
