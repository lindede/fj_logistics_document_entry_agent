# 开发计划（四里程碑）

依据：`requirements_understanding.md`、`module_design.md`、`flow_design.md`、`ui_design.md`。  
演示材料主稿：`docs/demo_pitch.md`。  
目标：按里程碑交付；下列状态以**当前仓库实现**为准。

| 里程碑 | 一句话目标 | 大致对应 | 状态 |
| --- | --- | --- | --- |
| **M1 能跑通** | 样例 PDF → 解析 → 校验 → 工作台确认/作废，主链路可演示 | 核心 P0 骨架 | 已完成 |
| **M2 校验与识别准确率** | 规则与主数据扎实；LLM 抽取可测、可迭代提准 | VAL/BR/MD + 评测 | 已完成 |
| **M3 加分/选做** | 动态指令、可观测、自动提交、MCP 风格、LangGraph 等 | P2 / 部分 P1 | 已完成 |
| **M4 Tool 服务 + Agent 服务** | Agent **只通过封装 Tool** 调解析/校验；可双进程分离 | API-01、AGT-01/02、TC-02 | **已完成** |

后续以 backlog / 演示打磨为主，不再开新的必做里程碑编号（除非试题范围外扩）。

---

## 里程碑 1：能跑通（End-to-End）— 已完成

### 目标

操作员用工作台上传样例 PDF，走完：开票 → 处理中 → 待确认/待人工 → 提交或作废；后端给出三件套；会话状态基本正确。

### 范围（做）

| 序号 | 工作项 | 模块 | 需求锚点 |
| --- | --- | --- | --- |
| 1.1 | 工程骨架：Python + FastAPI、配置、样例 PDF 入仓 | — | TC-01、DEMO-01 |
| 1.2 | 接入：HTTP `/api/parse_booking`；base64/路径判别；PDF 格式校验 | M-GW | API-01～03、TC-02/03 |
| 1.3 | 解析：PDF 文本层 + **LLM 抽取**；单据类型粗判 | M-PAR | PAR-01～04、BG-01 |
| 1.4 | 结构补齐：按 FLD 补全 key，缺省 `null` | M-PAR / M-VAL | VAL-04、FLD-* |
| 1.5 | 校验：结构检查 + **至少 3 条 BR** + report | M-VAL | VAL-05/08、BR-* |
| 1.6 | BookingRecord：三件套 + `meta` + `history` | M-AGT | DATA-01～03、VAL-08 |
| 1.7 | 会话：Idle → 解析/校验 → AwaitConfirm/Human → 提交或作废（提交后演进为 **Done**，见现状） | M-AGT | AGT-02/05、flow |
| 1.8 | 前端架子：顶进度 + 中区 + 底栏 | M-FE | BG-03、ui_design |
| 1.9 | 人工改字段 → 再校验（提交前 patch） | M-FE、M-VAL、M-AGT | UC-02 |
| 1.10 | 提交/持久化（`data/store`） | M-AGT | flow 提交节点 |

### 验收（M1）

- [x] 样例 PDF 开票，返回 raw / validated / report  
- [x] 工作台可见状态与结果，可提交或作废  
- [x] FAIL 样例进待人工，改后可再校验  
- [x] meta/history 基本写入  
- [x] 本地可演示 UC-01 / UC-02 / UC-04  

---

## 里程碑 2：数据验证 + LLM 识别准确率 — 已完成

### 目标

校验体系站稳；抽取准确率可量化、可回归。

### 范围（做）

| 序号 | 工作项 | 模块 | 需求锚点 |
| --- | --- | --- | --- |
| 2.1 | 补齐 BR；单位阈值表可配置 | M-VAL、M-MD | BR-*、TC-05 |
| 2.2 | 船名/港口白名单种子与接口 | M-MD | BR-03、BR-06 |
| 2.3 | Schema / 结构化输出与失败重试 | M-PAR、M-VAL | VAL-04 |
| 2.4 | 评测集：gold + FAIL/WARN 等变体 | — | PAR、VAL、DEMO |
| 2.5 | 准确率脚本与基线 | 脚本 | DEMO 准确率方案 |
| 2.6 | Prompt / 抽取迭代（vision 等） | M-PAR | BG-04、PAR-01 |
| 2.7 | 置信度进 report；低置信待人工 | M-VAL、M-PAR | VAL-06 |
| 2.8 | history/meta 可追溯 | M-AGT | DATA-02/03 |
| 2.9 | 人工修正回流 → `data/feedback` 回归用例 | M-AGT | VAL-07 |
| 2.10 | 前端报告与字段状态展示 | M-FE | UC-03 |

### 验收（M2）

- [x] ≥3 条确定性规则可演示  
- [x] `scripts/eval_accuracy.py` + `docs/eval_baseline.md`  
- [x] 提准手段可讲（见 `demo_pitch` / `booking_parse_summary`）  
- [x] 白名单未命中 → WARN 约定  
- [x] VAL-07：仅人工改字段后再提交写入 `feedback/<sid>/`  

---

## 里程碑 3：加分 / 选做 — 已完成

### 目标

原文进阶与体验增强（在 M1/M2 稳定后）。

| 序号 | 工作项 | 模块 | 落地现状 |
| --- | --- | --- | --- |
| 3.1 | 动态指令 ADV-01 | M-AGT、M-FE | **Done 态**底栏 NL → Function Calling → `amend_booking_record`（图外；Await 用表单） |
| 3.2 | 可观测 ADV-02 | M-OBS | `observe.timed` 等 |
| 3.3 | MCP 风格描述 | M-GW | `GET /api/mcp/tools` + 共用 `parse_booking`（非标准 MCP 协议） |
| 3.4 | `auto_on_pass` | M-AGT | `POST /api/config/submit_strategy` |
| 3.5 | 换票冲突 | M-AGT、M-FE | 进行中再上传询问 |
| 3.6 | 解析后端切换 | M-PAR | 配置项保留；主路径 multimodal |
| 3.7 | 视觉路径 | M-PAR | vision / pdf file_url |
| 3.8 | LangGraph 编排 | M-AGT | `booking_graph` + MemorySaver；`session_id=thread_id` |

### 验收（M3）

- [x] ADV-01、ADV-02 可演示  
- [x] MCP 风格 / 自动提交 / 冲突流可讲清并跑通  
- [x] 不破坏 M1/M2 评测主路径  

> 提交后业务态为 **Done**（只读）；作废 → Idle。强制提交为规则误拦时的应急出口（见 `demo_pitch` 工程边界）。

---

## 里程碑 4：Tool 服务 + Agent 服务 — 已完成

### 目标

解析+校验只通过 Tool 暴露；Agent（Session + LangGraph）开票经 Tool 门面/HTTP，不直连 extract。

### 范围与落地

| 序号 | 工作项 | 落地现状 |
| --- | --- | --- |
| 4.1 | Tool 门面 `parse_booking` | `process_booking` / HTTP；Agent `invoke_parse_booking` |
| 4.2 | LangGraph `parse` 只调 Tool | 已落地 |
| 4.3 | MCP 风格与门面对齐 | `/api/mcp/tools` |
| 4.4 | 双进程 | `APP_ROLE=tool`(:8001) + `APP_ROLE=agent`(:8000)；亦可 `all` 单进程 |
| 4.5 | 错误/耗时透传 | 与 OBS 一并可用 |
| 4.6 | 文档 | `demo_notes`、`demo_pitch`、README |

### 验收（M4）

- [x] 开票路径经 Tool，不直连抽数实现  
- [x] 外部 `POST /api/parse_booking` 与 Agent 共用门面  
- [x] 演示可讲：Tool = 解析治理；Agent = 会话与人机  
- [x] 双进程联调可跑通（`TOOL_BASE_URL`）  

---

## 现状会话要点（相对早期计划的演进）

| 项 | 当前约定 |
| --- | --- |
| 提交后 | **Done**（保留字段只读），不是回 Idle |
| 作废后 | Idle，可开新票 |
| 录入中改字段 | 点提交/强制提交前前端先 `patch` → 图内改字段→再校验 |
| Done 改字段 | 底栏指令，**不进**订舱 LangGraph |
| 自动提交 | 仅纯 PASS + `auto_on_pass` |
| 强制提交 | WARN/FAIL 时人确认后入库（应急） |

详情与图：`docs/demo_pitch.md`、`docs/flow_design.md`（若与实现冲突，以代码与 `demo_pitch` 为准，flow 待对齐 Done）。

---

## Backlog（非阻塞演示）

| 项 | 说明 |
| --- | --- |
| 更多版式家族 | 船司落货纸 / 十联单等；有稳定样张与规则再加（见 `struct_forms`） |
| vision + 文本拼写约束 | 页图看版面 + 文本层约束拼写（与已有 `html_mix` 不同路径） |
| flow_design 全文对齐 | 提交→Done、Done 指令图外等与实现一致 |
| 标准 MCP 协议 | 现为 HTTP + 风格描述，非 stdio/SSE 全协议 |
| Docling 等后端切换 | 配置预留，非演示主路径 |

---

## 建议节奏（已完成部分）

```text
M1 骨架跑通 ✓
  └─► M2 规则+评测+提准 ✓（含 VAL-07 feedback）
        └─► M3 选做加分 ✓（Done 指令 / AutoPass / LangGraph / MCP 风格）
              └─► M4 Tool + Agent 边界 ✓（门面 + 可选双进程）
                    └─► backlog / 演示打磨（pitch、flow 对齐等）
```

| 原则 | 说明 |
| --- | --- |
| 先竖切再挖深 | M1 全链路窄实现，M2 加深校验与准确率 |
| 评测驱动 | 没有 gold/脚本不谈「提升准确率」 |
| 选做可开关 | AutoPass 等可配置，默认不影响讲清主路径 |
| Tool / Agent 分离 | 已落地；演示讲调用边界即可 |

---

## 文档与演示产出

| 阶段 | 产出 | 状态 |
| --- | --- | --- |
| M1 | 可运行 Demo；README | 有 |
| M2 | `eval_baseline`；解析复盘 | 有 |
| M3 | 选做可演示 | 有 |
| M4 | 双角色启动；架构可讲 | 有 |
| 演示稿 | `docs/demo_pitch.md`（架构 / 核心逻辑 / 准确率） | 有 |

---

## 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-10-13 | 初版：M1 / M2 / M3 |
| 2026-10-13 | 记 VAL-07 回流；增补 M4 为下一步 |
| 2026-10-15 | 按现状刷新：M3/M4 已完成；Done 态与 ADV-01 图外修正；VAL-07 已落地；后续改为 backlog；链到 `demo_pitch` |
| 2026-10-17 | backlog：html/html_struct/html_mix 与版式分类已落地；待加更多家族 |
