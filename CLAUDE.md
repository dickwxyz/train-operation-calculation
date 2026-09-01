# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

铁路**调车作业计划**教学演示 Web 应用：输入到达列车（车号+去向列表）、分类股道数和目标编组顺序，用**分组选编法**自动生成调车作业计划表（解体→编组各钩的作业股道、摘挂、辆数、车号、说明），并展示最终出发编成。面向学校局域网内多名学生并发使用。

## 常用命令

```bash
# 首次：创建 venv 并安装依赖（flask + jieba）
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 启动服务（venv 内，threaded 多线程，监听 0.0.0.0:50000）
venv/bin/python app.py
# 访问 http://<服务器IP>:50000
```

本机系统 `/usr/bin/python3` 无 flask，须用 venv（已在仓库内创建，Python 3.12.7）。

- 端口固定为 **50000**（避开 macOS AirPlay 接收器占用的 5000）。
- **无测试、无 lint、无构建配置**。算法在 `scripts/shunting_plan.py` 中，不依赖 Flask，可脱离服务直接验证：

```bash
venv/bin/python -c "
from scripts.shunting_plan import ShuntingPlan
cars = [('H','乙'),('G','丙'),('F','甲'),('E','乙'),('D','丙'),('C','甲'),('B','乙'),('A','甲')]
r = ShuntingPlan(cars, 3, ['甲','乙','丙']).solve()
print(r['final_formation'], r['stats'])
"
```

- API 手动测试：`POST /api/solve`，JSON 体 `{cars:[{id,dest}], num_tracks, target_order}`，返回 `{success, steps, final_formation, stats}`。
- 教材问答：`POST /api/qa`，JSON 体 `{question}`，返回 `{answer, no_llm, sources:[{source, section, snippet}]}`；`no_llm:true` 或 `answer:null` 表示大模型未配置/调用失败，前端降级展示原文片段。LLM 配置见下方「教材问答」。

## 教材问答（LLM 配置）

问答流程：问题 → BM25 检索两章教材原文片段（`rag/retriever.py`）→ 拼 prompt → DeepSeek 生成回答。检索为纯 Python 零依赖，始终可用；只有生成回答需要 API Key。

- 配置在项目根目录 `.env`（环境变量优先）：`LLM_BASE_URL`（默认 `https://api.deepseek.com/v1`）、`LLM_API_KEY`、`LLM_MODEL`（默认 `deepseek-v4-flash`）。
- 从 `.env.example` 复制得到 `.env`，填好 `LLM_API_KEY` 后重启服务即生效。接口为 OpenAI 兼容，改 `base_url`/`model` 可换其他服务。
- `rag/` 各模块均可独立测试（`python -c`），不依赖 Flask。

## 架构与约定

### 代码分层

- `app.py` — Flask 入口。`/` 返回前端页面，`/api/solve` 做输入校验后调用求解器。校验规则（车号非空/去重、至少 2 辆、股道数 2~6 的整数、所有去向必须出现在目标顺序中）**前后端各有一份**，改输入规则需同步两处。
- `scripts/shunting_plan.py` — `ShuntingPlan` 求解器，纯算法无 I/O。四个私有方法对应算法流程：`_allocate_tracks`（去向→股道分配）→ `_break_up`（解体）→ `_make_up`（编组）→ `_build_result`（汇总统计）。`app.py` 通过 `from scripts.shunting_plan import ShuntingPlan` 引用。
- `static/index.html` + `static/qa.html` + `static/style.css` — 前端单页（原生 JS，无框架）：`index.html` 为求解页，`qa.html` 为教材问答页（`/` 和 `/qa` 路由直接 `send_static_file` 分发，**无 `templates/` 目录**）。
- `rag/` — 教材问答后端（纯 Python，零第三方依赖）：`corpus.py` 把两章教材原文按标题分块、`tokenizer.py` 中文分词（有 jieba 用之，否则字符二元组回退）、`retriever.py` BM25 检索（惰性建索引）、`llm.py` 调 DeepSeek、`config.py` 读 `.env`、`qa.py` 编排问答。
- `knowledge_base/` — 教材知识库（Markdown 提炼）：章节梳理、术语表、**算法方法与代码对照**（教材调车表法 vs 本求解器的差异与改进方向，改算法前必读）、算例集。

### 核心算法约定（务必遵守，改动前先读 `1test.md` 第 6 节）

1. **车辆输入顺序 = 机车端在前**：`cars[0]` 是机车端，`cars[-1]` 是尾部。前端表格展示时最下方一行才是机车端（`getCarsFromTable()` 从表尾反向收集）。
2. **去向→股道分配按目标顺序**：目标顺序第 i 个去向 → `"{i+1}道"`。`_allocate_tracks` 先按 `target_order` 去重分配，再把出现在车辆中但不在目标顺序里的去向补到末尾；去向数超过股道数时抛 `ValueError`。
3. **`track_states[track]` 存储方向 = 外方→内方**（索引 0 为外方/靠近机车端）。解体时新挂车用 `insert(0, ...)`；编组牵出顺序就是列表本身顺序，**不能 `reversed`**。这是历史上踩过的坑（见 `1test.md`：曾把 `F→C→A` 编成 `A→C→F` 的反向 bug）。
4. 步骤 `phase` 取值：`牵出` / `解体` / `编组`；`op` 取值 `+`（挂车/牵出至牵出线）/ `-`（摘车/分解）。

### 已知问题

- Flask 开发服务器 `debug=True` 仅适合教学演示；并发量级是毫秒级计算，`threaded=True` 够用。
- 两章教材 PDF 提取的文本含 OCR 噪声（如 `t节` 误写为 `t书`/`t特`、公式混排），`knowledge_base/` 中已按上下文统一符号，但 `assets/` 原文检索语料仍保留原文写法。

## 参考资料

`assets/` 存放教科书《铁路行车组织》（第 2 版）及其章节摘录（PDF + 提取的 Markdown + 图片）：
- `铁路行车组织第2版-调车计划/` — **第四章 调车工作**（分组选编法的原理出处）
- `铁路行车组织第2版-技术站列车编组计划的编制/` — **第十一章 技术站列车编组计划的编制**

`knowledge_base/` 是这两章的**结构化提炼**（术语表、算法与代码对照、算例集），检索问答的语料则是 `assets/` 中的教材原文。

`1test.md` 是该项目的开发对话实录，包含算法原理讲解、手工算例、编组顺序 bug 的排查过程、端口调整，是理解设计与历史决策的第一手资料。

## 开发日志（无版本控制）

本目录**不是 git 仓库**，无提交历史可查。`1test.md` 是唯一的变更记录，新增重要改动时应考虑同步补充。
