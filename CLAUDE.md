# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

铁路行车组织教学演示 Web 应用，三页共用顶部标题「铁路行车组织算例教学演示」与标签页「调车作业计划 / 列车编组计划 / 教材问答」：

- **调车作业计划（`/`）**：按《铁路行车组织（第2版）》第四章第五节的「调车表法」求解——输入待编车列与股道条件，自动完成 **下落 → 调整(邻组) → 暂合候选 → 股道分配 → 逐钩作业计划**，并分阶段展示、用逐步股道图回放每钩后的股道/牵出线状态。
- **列车编组计划（`/bianzu`）**：第十一章技术站单组列车编组计划算例页——选题后按算例集步骤展示绝对计算法/表格计算法的完整表格、列车到达站图、最优方案与目标函数值（静态生成页，见「编组计划算例页」）。
- **教材问答（`/qa`）**：教材检索 + 大模型问答。

前端为原生 JS 静态页，无构建、无模板目录。

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
- 编组算例页是生成产物，重跑即同时回归：
  ```bash
  venv/bin/python scripts/build_bianzu_page.py
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
`MODE="locked"` 时，**非例题**输入在解析后被 `scripts/mode.py` 的白名单闸门拦下，返回 **403**（见「教学版锁定」）；**当前 `MODE="full"`，闸门不生效**——习题与自编数据都能求解。

### `GET /api/mode`

返回 `{mode, exercise_locked, locked_names}`。前端载入时拉一次，据此决定习题按钮是否放开；**接口不可达时前端按锁定降级**（fail-closed）。

### `POST /api/bianzu`（编组算例重算，可选）

> 页面已改为**纯前端 JS 计算**（见「编组计划算例页」），不再调用此接口；保留供其他客户端使用。

请求：`{key, T:[…], t:{"1":4,…}, N:{"31":95,…}}`（只允许改数值；题目与车流名固定）。
返回 `{success, html}`；参数错误 400。默认数据返回教材定稿 panel；修改后的数据走 Python 通用求解器。
实现：`scripts/build_bianzu_page.py` 的 `render_bianzu_panel()`；路由在 `app.py`。

### `POST /api/qa`（教材问答）

`{question}` → `{answer, no_llm, sources[]}`。语料路径当前失效（见「已知问题」），查询会报错——问答本次不在维护范围。

## 架构与约定

### 代码分层

- `app.py` — Flask 入口，`send_static_file` 分发 `/`、`/qa`、`/bianzu`（及 `/svg/bianzu/*`）（**无 `templates/`**）；`/api/solve` 校验后调 `scripts.shunting_plan.ShuntingPlan`。
- `scripts/`（纯 Python、零第三方、单向依赖）：
  - `parser.py` → `model.py` → `xialuo.py`（下落）→ `tiaozheng.py`（邻组化调整）→ `engine.py`（逐钩物理模拟+快照）→ `planner.py`（枚举暂合/股道分配/调度/择优）→ `shunting_plan.py`（门面）。
  - `fixtures.py` 依赖全部，仅测试。
  - `simulator.py` 提供 engine 使用的基础原语（`pull_part`/`pull_all`/`throw`/`transfer` + 状态快照）。
  - `mode.py` — 运行模式与**例题白名单闸门**（纯 Python），只被 `app.py` 调用；库层刻意不设闸（教师本地验算与 fixtures 回归不受影响）。见「教学版锁定」。
  - `build_bianzu_page.py` — 生成 `/bianzu` 静态页与到达站图；页面内嵌 JS 求解器（`RUNTIME_JS`），并将题目数据序列化为 `bz-data` JSON；同时提供 `render_bianzu_panel()` 给可选 API。内含教材算例断言。
  - `编组方案svg绘图/` — `draw_scheme.py`（到达站图 SVG 生成器，`SCHEMES` 定义默认题方案）+ 教材图源 PNG/SVG；默认页面用图由 `build_bianzu_page.py` 调用其 `build()` 生成，运行时图由同一函数动态构造。
- `static/` — `index.html` 求解页、`qa.html` 问答页、`bianzu.html` 编组算例页（生成产物）、`svg/bianzu/` 到达站图、`style.css`。
- `rag/` — 问答后端（corpus/tokenizer/retriever/llm/config/qa），语料路径失效，暂不维护。
- `knowledge_base/调车工作/` — 教材第四章结构化提炼（提炼/术语表/算例集/原文 md/images）。
- `knowledge_base/技术站列车编组计划的编制/` — 第十一章原文/提炼/术语表/算例集与 images/；`/bianzu` 的数据与算例步骤依据。
- `assets/` — 教材 PDF（版权，gitignore 未跟踪）。`过程/`（gitignored）— 开发实录（第十一章资料已迁至 `knowledge_base/`）。

### 堆序约定（全项目唯一，务必遵守）

> **任意股道 / 牵出线状态一律「机车远端(内/左) → 机车端(右)」，机车端恒在右。** 待编车列书写序 = 该序（索引 0 = 最远/内）。编成目标 = 去向 1..n 顺序、n 贴机车端。记号 `k_m` = 去向 k 的 m 辆车（一个车组，原子单元）。

前端逐步股道图与后端 `state.tracks[t]/state.lead` 同向；改渲染或模拟时不要弄反（旧"分组选编法"曾用相反约定，勿照搬旧文档）。

### 编组计划算例页（`/bianzu`）

- **产物**：`static/bianzu.html` + `static/svg/bianzu/*.svg`，由 `scripts/build_bianzu_page.py` 生成；**不要手改产物**，改数据/版式后重跑脚本。默认数据的结果是构建期定稿；修改数据后的重算在浏览器内完成（`RUNTIME_JS`），不依赖后端，file:// 直接打开也可用。
- **选择 UI**：与 `index.html` 一致的预设按钮行——「例题：例11.3/11.5/11.6」「习题：习题1/2/3」；点击后在选择卡内显示该题的**可编辑表单**（T集、t节、非短途车流车数，均为文本框，无上下箭头）与默认 panel，其余 `hidden`；当前按钮高亮。支持 `#p-ex11.3` / `#p-xt3` 等 hash 直接打开。
- **编辑重算（纯前端）**：表单下方「计算列车编组计划」在浏览器内调用 `BZ.renderPanel()`，替换对应 panel 的 `innerHTML`，不发网络请求；切换题目时 `form.reset()` 并恢复构建期 panel。默认数据完全一致时直接恢复教材定稿 panel；有改动时走 JS 通用求解器（初始方案 → 全枚举最优 → BFS 调整路径 → 动态 SVG 内联）。后端 `/api/bianzu` 仅为可选入口。
- **通用求解器**：Python 版（`initial_combo()` / `optimal_combo()` / `improvement_path()` / `diagram_scheme()`）与页面内嵌 JS 版（`RUNTIME_JS`）同模型、各一份，改算法需两边同步。初始方案按绝对/必要条件（单开 + 合并必要条件分组 + 并入终点 ≤ 去向的现有直达块/相邻列）；全枚举找最优；BFS 找 F节 严格增加的路径（失败退回贪心并追加全枚举最优）；运行时到达站图内联 SVG，marker id 逐图加后缀。
- **单题内容顺序**：绝对计算法（仅 4 站题：第一步枚举、第二步 10 个方案各一张完整计算表 + 到达站图、第三步选 F耗 最小）→ 表格计算法（第1步 N通·t节 表；第2步「（1）绝对条件的判断 →（2）必要条件①的判断（式 11.13）→（3）必要条件②的判断——剩余车流的合并（式 11.14，只针对（1）（2）都不满足的剩余车流，交集仅有相邻区段者只能编入摘挂列车）」+ 初始方案表/图 + F节 + 验证；第3步逐个调整；第4步选最优）→ 结论。**方案的 desc 与结论只写开行的非短途直达列流（发站编号−到站编号 ≥ 2）**，相邻站间的摘挂列车不写。已知信息只出现在选择卡，不再放进计算 panel。
- **表格格式**：与 `技术站列车编组计划的编制-算例集.md` 一致——标签 `colspan=2`（空 + 首站），随后各站数值列；公共行序为 `T集`、`t节`、各车流。**绝对计算法**的表随后是 `N改编`、`N改编·t节` 两行；**表格计算法**的表不含这两行，而在同位置放一行 `ΣN<sub>通</sub>·t<sub>节</sub>`：每个中间站一列填该站 ○/△ 记号值之和（式 11.9 的 `N通^w·t节^w`），最后一列（A0 列）填总计（= F节 的被减数）。随后是各站 `K_i·T集^i` 与目标函数行。运行时数值用 `fmt()` 去掉多余的 `.0`。
- **条件判定**：绝对条件按教材式 (11.11) `N_ij · min{t_k} ≥ T集^i`（**min，不是 max**）；必要条件 (11.13) `N_ij · Σt_k ≥ T集^i`。表格中满足绝对条件的车流在**所有**无改编通过的格子里标 △，其余无改编通过标 ○。
- **计算内核**：站点编组方案 = 该站出发车流的一个划分，块内列车终点 = 最近到站；车流按接续归并走行，每次换乘计一次改编。4 站枚举 10 个方案、5 站 150 个方案；`F耗 = ΣN改编·t节 + Σk_i·T集^i`，`F节 = ΣN通·t节 − Σk_i·T集^i = C − F耗`。
- **数据/断言**：`PROBLEMS`（6 题数据与各阶段 F节/F耗 期望）、`P4_ORDER`（4 站 10 方案）、`P5`（5 站各阶段划分）。改数据时必须同步各阶段期望值，脚本会逐项断言；5 站题还会用全枚举最小值校验最优方案。`build()` 另含通用求解器回归：默认数据下 `initial_combo()` 必须等于教材初始方案、全枚举最优 F耗 与定稿一致。
- **默认图**：页面用到的方案名必须存在于 `scripts/编组方案svg绘图/draw_scheme.py` 的 `SCHEMES`（当前含 11.9.1–11.9.10、11.20–11.23、xt2/xt3、xt2_init/xt3_init/xt3_s1，共 19 个）；运行时图不依赖这些名字，由 `diagram_scheme()` 动态构造。默认题新增图在 `SCHEMES` 里定义，不要在 HTML 里手画。
- **默认数据 vs 修改数据**：默认 6 题使用教材定稿的步骤与图；修改数据后的初始方案/调整路径由通用求解器生成，过渡步骤可能与教材人工调整顺序不同，但目标函数值与全枚举最优一致。

### 教学版锁定（例题白名单，开发时定死）

> **当前 `MODE = "full"`（2026-09 放开）**：作业一收齐后，6 个习题按钮已在页面上可点、答案可算。
> 闸门代码原样保留，改回 `"locked"` 重新打包即恢复课堂锁定。下面描述的是**锁定态**的行为。

课上先讲 3 个例题，6 个习题（习题2/3/7/8/9/12）留给学生自己做。锁定**在开发时定死**，学生端无法更改：

- **开关**：`scripts/mode.py` 顶部 `MODE = "locked" | "full"`。切换＝改常量 + 重新打包上传；启动时日志打印当前状态。
- **白名单**：锁定版**只放行 3 个例题**（`ALLOWED_EXAMPLES`，由 `parser.PRESETS` 派生），其余输入一律 403。
- **判定用规范形** `mode.canonical(groups)`：逐辆去向 → **首次出现次序**。它对三种变形都不变，所以绕不开：
  - **站号重命名**（任意 `station_order`，如 `7654321`）—— 早先按 `(去向, 辆数)` 比对时会漏，用户实测可绕过；
  - **车组边界改写**（`1₃` ↔ `1 1 1`）；
  - **书写格式**（下标 / `4_2` / 空格 / 逗号；`parse_seq` 已先归一）。
- **闸门在服务端**：`app.py` 的 `/api/solve` 在 `parse_seq` 之后判 `mode.is_allowed(groups)`。前端置灰只是观感层——改 JS 或直调 API 一样被拦。
- **前端**：6 个习题按钮在 HTML 里写死 `disabled`（脚本报错、接口不通时仍是灰的，fail-closed）；`/api/mode` 回报 `exercise_locked: false`（即 `MODE="full"`）时前端解除置灰并清空锁定 title，锁定态则按 `example_only` 在输入区显示"仅开放例题"提示。
- **代价**：锁定版下**任何非例题输入都会被拒**——学生无法用自编数据练习，课堂变式也做不了。这是刻意取舍：黑名单要追着学生的变形跑，白名单只需认死例题。
- `fixtures.run()` 第 5 节即闸门回归，**断言一律显式传 `locked=True`**，因此与出厂 `MODE` 无关——`"full"` 下机制仍被守着，改回 `"locked"` 即生效。含**前端 `index.html` PRESETS 防漂移**断言（前后端题干不一致会 FAIL）与 `mode_payload` ↔ `MODE` 自洽断言。
- **新增任何暴露求解能力的 HTTP 入口，都必须过 `mode.is_allowed()`。**

### 算法流程（改动前先读 `knowledge_base/调车工作/调车工作-算例集.md`）

1. **下落** `xialuo.py`：逐列（基准=上列末车组去向，无反顺序则续落 v+1…）；每列去向非降。断言对表 4.5/4.9/4.16。
2. **调整** `tiaozheng.adjust_with_moves`：把"列首/末可调车组"在其右邻(v+1 同邻列)时移入相邻列成**邻组**；**保护 home 列坐底前缀**。复现表 4.6/4.17；例4.4 无需调整。planner **默认先调整再调度**。
3. **暂合**：对口理论（列一不并入；相邻列一般不并；尽量邻组/机前集结）；股道不足时允许更密合并。
4. **股道分配**：含首车组列的超列坐底于停留道；其余给 allowed 其他道。
5. **钩计划** `engine.py`：初牵留坐底 → 溜放(同目标股道连续车段合一钩，保留机前集结=属 home 超列或最大去向的近机尾段) → messy 超列(≥2 列)整列牵出再按"最近更低列所在超列"归块 → 非空股道按去向区间降序连挂 → 转线。
   `engine.schedule(...)` 返回逐钩 `HookStep`（含 `state` 快照）与 `Stats`。
   **轮次** `HookStep.round`＝每次"股道牵出 / 转线"开一轮，该轮内的溜放（含拆分归块）沿用本轮号；前端"第 N 轮 / 跳轮"即按此归组。

## 已知问题 / 限制

- **闸门只挡 `/api/solve`**：`/api/qa`（RAG 修复后）目前不过闸——若语料将来含习题答案，需一并接入 `mode.is_allowed()`。前端 JS 与 `index.html` 里仍有 6 个习题的**原题**（`view-source:` 可见），那是教材上的题面、不是答案，属可接受；答案从未下发到前端（拦截发生在 `jsonify(result)` 之前）。当前 `MODE="full"`，闸门本就未生效。
- 例4.4 **三列合并（二·四·五）**与**习题3（最多 3 条线）**：当前调度引擎对"三列暂合/极紧预算"仍无可行方案（页面提示无可行方案）。
- 自动调整只做单对边界邻组；非教材算例钩数为引擎实测（正确可运行），未必等于某人工最优。
- **RAG 语料路径失效**：`rag/corpus.py` 的 `SOURCES` 指向 `assets/…/*.md`（不存在）。需要时改指实际 md（第四章 `knowledge_base/调车工作/铁路行车组织第2版-调车工作.md`；第十一章 `knowledge_base/技术站列车编组计划的编制/铁路行车组织第2版-技术站列车编组计划的编制.md`）。
- Flask `debug=True` 仅教学；并发小、`threaded=True` 够用。教材 OCR 原文有少量噪声（如 `t节`），`knowledge_base` 已统一符号。
- 本目录是 git 仓库（`main`）。文档改动请同步本文件与 `README.md`。

## 参考资料

- 教材原理：`assets/铁路行车组织第2版-调车工作.pdf`（第四章）、`assets/铁路行车组织第2版-技术站列车编组计划的编制.pdf`（第十一章）。
- 结构化提炼与算例：`knowledge_base/调车工作/`（提炼、术语表、算例集——含例4.3 三种暂合的逐轮 S1–S5 状态验证真源）。
- 第十一章：`knowledge_base/技术站列车编组计划的编制/`（原文、提炼、术语表、算例集、images/）——`/bianzu` 的数据与步骤依据。
- 开发过程实录：`过程/chat1.md`、`过程/算例调车.md`（gitignored）。

## 待办 / Roadmap（2026-09）

按优先级/依赖建议顺序：

1. **手算验证 例4.4 / 例4.6**：对照教材表 4.10 / 4.12 / 4.20 逐钩手算，核对引擎输出（钩数/股道分配/终列）。
   若有不符 → 把核对过的算例整理进 `knowledge_base/调车工作/调车工作-算例集.md`，据以修正 `engine.py`
   与 `planner.py`，并同步更新 `scripts/fixtures.py` 断言。
2. **三股道 / 三列合并调度**：当前 `engine.py` 对「三列暂合（如例4.4 二·四·五）与极紧预算（习题3 ≤3 线）」
   无可行方案；需扩展 messy 超列的拆分（可把刚清空的自身股道当缓冲块）与更紧预算的暂合枚举。
3. **RAG 问答页与语料**：先修 `rag/corpus.py` 的 `SOURCES`（第四章 → `knowledge_base/调车工作/铁路行车组织第2版-调车工作.md`，
   第十一章 → `knowledge_base/技术站列车编组计划的编制/铁路行车组织第2版-技术站列车编组计划的编制.md`），再完善 `/qa` 页面与降级提示。
4. **第十一章《列车编组计划》**：知识库已迁至 `knowledge_base/技术站列车编组计划的编制/`；`/bianzu` 已覆盖
   例11.3/11.5/11.6 与习题1/2/3 的双算法完整过程。后续可补例11.4、其余习题、超过 5 个支点站的算例，
   以及更紧凑的表格排版（当前每个方案一张完整表，页面较长）。

改算法前先读「架构与约定 → 算法流程」与 `knowledge_base/调车工作/调车工作-算例集.md`。
