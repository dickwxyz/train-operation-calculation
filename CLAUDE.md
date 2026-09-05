# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

铁路**调车作业计划**教学演示 Web 应用：按《铁路行车组织（第2版）》第四章第五节**按站顺编组摘挂列车的「调车表法」**求解——输入待编车列与股道条件，自动完成 **下落 → 调整(邻组) → 暂合候选 → 股道分配 → 逐钩作业计划**，并分阶段展示、用逐步股道图回放每钩后的股道/牵出线状态。前端为原生 JS 单页，无构建、无模板目录。

## 常用命令

```bash
# 首次：venv + 依赖（flask；jieba 可选）
python3 -m venv venv && venv/bin/pip install -r requirements.txt

# 启动服务（threaded，监听 0.0.0.0:50000）
venv/bin/python app.py
# 访问 http://<服务器IP>:50000
```

- 端口固定 **50000**（避开 macOS AirPlay 占用的 5000）。本机 `/usr/bin/python3` 无 flask，须用 `venv`（Python 3.12.7）。
- **无 pytest / lint / 构建**。算法核心不依赖 Flask，直接验证/回归：
  ```bash
  PYTHONPATH=. venv/bin/python -c "from scripts import fixtures; fixtures.run()"
  ```
- API 手动测试（curl）见下节；也可起服务后在浏览器点例题/习题按钮。

## API

### `POST /api/solve`（调车表法）

请求体：
```jsonc
{ "seq": "4₂5₂6₁3₁5₂1₃2₁4₃3₂6₁5₁3₂1₁4₂7₂",
  "station_order": null,             // 字母站名时的编成顺序，如 "fedcba"
  "home_track": "7",
  "allowed_tracks": ["7","8","9","10"],   // 与 track_budget 二选一（含停留道）
  "track_budget": 4,                 // 最多作业线路条数（含停留道）
  "depart_track": "DF3",
  "weights": {"pull":4,"throw":1,"transfer":1} }  // 可选，默认如上
```
响应：
```jsonc
{ "success": true,
  "meta": { parsed_seq, total_cars, max_station, group_totals, home_track,
            allowed_tracks, depart_track },
  "stages": { "xialuo": {header, cols},              // 原始下落表
              "tiaozheng": {note, moves, cols_after}, // 邻组化调整
              "track_budget": {limit} },
  "schemes": [ { id, label, supercols, track_alloc, stats, hooks, final_formation, best } ],
  "best_scheme_id": "s0" }
```
`stats = {hooks_pull, hooks_throw, hooks_transfer, total_hooks, textbook_total, cheng, weighted, tracks_used}`；
每钩 `hooks[j] = {seq, code, op, track, qty, kind(挂/溜/转), phase_round, note, cars, state}`，`state={tracks, lead}` 为该钩后全场（前端直接渲染，零再推导）。
**前后端输入校验各一份**（`app.py` 与 `static/index.html` 的 `validateInput`/`buildPayload` 镜像），改输入规则需两处同步。

### `POST /api/qa`（教材问答）

`{question}` → `{answer, no_llm, sources[]}`。语料路径当前失效（见「已知问题」），查询会报错——问答本次不在维护范围。

## 架构与约定

### 代码分层

- `app.py` — Flask 入口，`send_static_file` 分发 `/` 与 `/qa`（**无 `templates/`**）；`/api/solve` 校验后调 `scripts.shunting_plan.ShuntingPlan`。
- `scripts/`（纯 Python、零第三方、单向依赖）：
  - `parser.py` → `model.py` → `xialuo.py`（下落）→ `tiaozheng.py`（邻组化调整）→ `engine.py`（逐钩物理模拟+快照）→ `planner.py`（枚举暂合/股道分配/调度/择优）→ `shunting_plan.py`（门面）。
  - `fixtures.py` 依赖全部，仅测试。
  - `simulator.py` 提供 engine 使用的基础原语（`pull_part`/`pull_all`/`throw`/`transfer` + 状态快照）。
- `static/` — `index.html` 求解页、`qa.html` 问答页、`style.css`。
- `rag/` — 问答后端（corpus/tokenizer/retriever/llm/config/qa），语料路径失效，暂不维护。
- `knowledge_base/调车工作/` — 教材第四章结构化提炼（提炼/术语表/算例集/原文 md/images）。
- `assets/` — 教材 PDF（版权，gitignore 未跟踪）。`过程/`（gitignored）— 开发实录与第十一章原文 md。

### 堆序约定（全项目唯一，务必遵守）

> **任意股道 / 牵出线状态一律「机车远端(内/左) → 机车端(右)」，机车端恒在右。** 待编车列书写序 = 该序（索引 0 = 最远/内）。编成目标 = 去向 1..n 顺序、n 贴机车端。记号 `k_m` = 去向 k 的 m 辆车（一个车组，原子单元）。

前端逐步股道图与后端 `state.tracks[t]/state.lead` 同向；改渲染或模拟时不要弄反（旧"分组选编法"曾用相反约定，勿照搬旧文档）。

### 算法流程（改动前先读 `knowledge_base/调车工作/调车工作-算例集.md`）

1. **下落** `xialuo.py`：逐列（基准=上列末车组去向，无反顺序则续落 v+1…）；每列去向非降。断言对表 4.5/4.9/4.16。
2. **调整** `tiaozheng.adjust_with_moves`：把"列首/末可调车组"在其右邻(v+1 同邻列)时移入相邻列成**邻组**；**保护 home 列坐底前缀**。复现表 4.6/4.17；例4.4 无需调整。planner **默认先调整再调度**。
3. **暂合**：对口理论（列一不并入；相邻列一般不并；尽量邻组/机前集结）；股道不足时允许更密合并。
4. **股道分配**：含首车组列的超列坐底于停留道；其余给 allowed 其他道。
5. **钩计划** `engine.py`：初牵留坐底 → 溜放(同目标股道连续车段合一钩，保留机前集结=属 home 超列或最大去向的近机尾段) → messy 超列(≥2 列)整列牵出再按"最近更低列所在超列"归块 → 非空股道按去向区间降序连挂 → 转线。
   `engine.schedule(...)` 返回逐钩 `HookStep`（含 `state` 快照）与 `Stats`。

## 已知问题 / 限制

- 例4.4 **三列合并（二·四·五）**与**习题3（最多 3 条线）**：当前调度引擎对"三列暂合/极紧预算"仍无可行方案（页面提示无可行方案）。
- 自动调整只做单对边界邻组；非教材算例钩数为引擎实测（正确可运行），未必等于某人工最优。
- **RAG 语料路径失效**：`rag/corpus.py` 的 `SOURCES` 指向 `assets/…/*.md`（不存在）。需要时改指实际 md（第四章 `knowledge_base/调车工作/铁路行车组织第2版-调车工作.md`；第十一章 `过程/…/…md`）。
- Flask `debug=True` 仅教学；并发小、`threaded=True` 够用。教材 OCR 原文有少量噪声（如 `t节`），`knowledge_base` 已统一符号。
- 本目录是 git 仓库（`main`）。文档改动请同步本文件与 `README.md`。

## 参考资料

- 教材原理：`assets/铁路行车组织第2版-调车工作.pdf`（第四章）、`assets/铁路行车组织第2版-技术站列车编组计划的编制.pdf`（第十一章）。
- 结构化提炼与算例：`knowledge_base/调车工作/`（提炼、术语表、算例集——含例4.3 三种暂合的逐轮 S1–S5 状态验证真源）。
- 开发过程实录：`过程/chat1.md`、`过程/算例调车.md`（gitignored）。
