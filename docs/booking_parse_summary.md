# Booking 解析提取：问题、改动与优化总结

面向托运单 PDF → 结构化订舱字段的解析链路（`parse_booking` / `process_booking` / `parse_pdf_bytes`）。  
本文汇总实践中碰到的问题、已做修改、调试手段、当前结论，以及待试方向，便于复盘与面试口述。

---

## 1. 目标与边界

**目标**：从出口货物托运单 PDF 抽出业务字段（发货人、收货人、通知方、船名航次、装卸港、箱型箱量、件数毛重体积、运费等），经规整与校验后进入人工确认 / 提交。

**边界**：

- 解析在 **Tool** 侧完成（`APP_ROLE=tool`，`POST /api/parse_booking`）。
- **Agent** 只通过 Tool 门面开票，不直连 extract。
- 单测默认 `PARSE_BACKEND=fixture`（测管道）；真抽准度依赖 LLM + gold / prompt_lab。
- 规则抽取（`html_struct`）按**运单版式家族**分派；未识别版式不套用 BKG 规则。

---

## 2. 当前数据流

```text
PDF
  ├─ pypdf 文本层 …… 单据门禁、调试对照（html/html_struct/html_mix 不靠它当主输入）
  └─ 抽数（PARSE_BACKEND=llm 时看 LLM_INPUT_MODE）
        pdf         = file_url 整份 PDF → OPENAI_MODEL（多模态）
        vision      = PyMuPDF 渲 PNG 页图 → OPENAI_MODEL
        text        = 纯文本 → OPENAI_TEXT_MODEL（丢版面，不推荐主路径）
        html        = 文字坐标 HTML（无框线）→ OPENAI_TEXT_MODEL
        html_struct = 版式分类 + 坐标/矩形规则抽取（不调大模型）
        html_mix    = 先 classify+struct，再 html LLM；主结果用 LLM
           │
           ├─ form_family …… 版式家族（html_struct / html_mix）
           ├─ html_struct_raw …… 结构侧字段（html_mix；未知版式为 {}）
           ├─ mix_diff_issues …… MIX-DIFF / MIX-FORM（html_mix）
           ├─ llm_analysis …… staged「### ANALYSIS」叙述（LLM 路径）
           ├─ raw_extracted_data …… 模型 JSON 原样或规则结果（不做 normalize）
           ├─ normalized_data …… 约定规整（运费 P/C/E、唛头、航次等）
           └─ validate → validated_data + validation_report
                 └─ html_mix 的 MIX-* 并入 issues；仅有 MIX 且原 PASS → overall WARN
```

关键代码：

| 环节 | 位置 |
|------|------|
| 抽数 / 模式切换 | `app/parse/extract.py` |
| 文字坐标 HTML | `app/parse/html_layout.py`（`words_to_html`） |
| 结构几何与数字拆分 | `app/parse/html_struct.py` |
| 版式家族注册 | `app/parse/struct_forms/` |
| 货代出口 SO 规则 | `app/parse/struct_forms/forwarder_export_so.py` |
| html_mix 对照 | `app/parse/html_mix.py` |
| 文本层 | `app/parse/pdf_io.py`（`pypdf`） |
| 页图 | `app/parse/pdf_pages.py`（PyMuPDF → PNG） |
| 解析+校验门面 | `app/booking/process.py` |
| 分层字段模型 | `app/models.py`（`BookingRecord`） |

### 2.1 `LLM_INPUT_MODE` 一览

| 模式 | 是否调 LLM | 需要文字层 | 说明 |
|------|------------|------------|------|
| `pdf` | 是（视觉模型） | 否 | 默认；`file_url` 直传 |
| `vision` | 是（视觉模型） | 否 | 自渲页图；扫描件常用 |
| `text` | 是（文本模型） | 是 | 无文字层时会强制改 `pdf` |
| `html` | 是（文本模型） | **是** | 坐标 HTML；无文字层直接报错，不静默回退 |
| `html_struct`（别名 `xtml_struct`） | **否** | **是** | 先分类再规则抽取；未知版式报错 |
| `html_mix` | 是（文本模型） | **是** | LLM 为主；结构侧对照；LLM 失败整单失败 |

文字层很薄时：仅 `text` 会强制切到 `pdf`；`html` / `html_struct` / `html_mix` **不会**静默改成 pdf/vision。

### 2.2 版式家族（`html_struct` / `html_mix`）

分类在抽字段**之前**。每个家族的**识别条件与提取规则同包**；共享几何、线框、`split_number_unit` 仍在 `html_struct.py`。

| `form_family` | 识别要点 | 行为 |
|---------------|----------|------|
| `forwarder_export_so` | 发货人标题落在矮矩形标题条内，且有收货人、装货港标签 | 按 BKG 一类货代出口托运单规则抽字段 |
| `unknown` | 无一家族命中 | `html_struct`：**抛错**「未识别运单版式」；`html_mix`：结构侧空字段，记一条 `MIX-FORM` WARN，**不**对每个空字段刷 MIX-DIFF |

新增家族：在 `app/parse/struct_forms/` 增加模块，并挂进 `__init__.py` 的 `_FAMILIES`。不要把未知版式硬套现有规则。

样张大致归类（教学用，非实单）：

| 样张 | 家族 |
|------|------|
| `data/samples/BKG.pdf` | `forwarder_export_so` |
| `cn_shipping_orders/cn_export_shipping_order_filled.pdf` | `forwarder_export_so` |
| `cn_shipping_orders/cn_container_dock_receipt_filled.pdf` | `forwarder_export_so` |
| `cn_shipping_orders/cn_shipping_order_blank_template.pdf` 等无标题条版式 | `unknown` |
| COSCO Taiwan 空白/叠印 | `unknown` |

### 2.3 `html_mix` 对照规则

- 主结果始终是 **html LLM** 侧（经 normalize 后进校验）。
- 已知版式：两侧 normalize 后按字段比；不一致 → `MIX-DIFF` WARN，文案含两侧值：`html_struct=… / html=…`。
- `voyage` 的 `null` 与 `""` 视为相等；两侧都空相等；一侧空一侧有值算不一致。
- `containers` 比 type / qty。
- 业务规则 FAIL 仍优先于 MIX 警告。
- LLM 调用失败：整单失败，**不**回退成只用 struct。

### 2.4 数字与单位（规则侧）

`split_number_unit`：**只有**「纯数字 + 已知单位」且两段拼接与原文逐字相同才拆开（如 `25600KGS`）。  
`2560OKGS` / `A320KGS` 整段留在数值字段，供校验暴露错误。  
裸数字（如 `32.03`）单位只取**该列表头**打印的单位，不默认编造 KGS/CBM。

表单侧：非规范数字用 `type=text` 展示与提交，禁止 `<input type="number">` 把脏串清空。

---

## 3. 提示词策略

- 生产 LLM 路径采用 **分阶段输出**：同一次回复内先 `### ANALYSIS`，再 `### JSON`。
- 字段必须与 ANALYSIS 对齐；规则含 voyage 不要带 ETD/电话、freight 规整为 P/C/E 等。
- `pdf` / `vision` 共用视觉侧规则；`html` 用坐标 HTML 专用说明（notify 只取 Notify 标题同左栏等）。
- `html` / `html_mix` 的聊天模型为 `OPENAI_TEXT_MODEL`（演示常用 `glm-5.3`）；`pdf` / `vision` 为 `OPENAI_MODEL`（如 `glm-4.6v`）。
- prompt 实验室：`data/prompt_lab/` + `scripts/prompt_lab_run.py`（pdf/vision）、`prompt_lab_html_run.py`（html）、`prompt_lab_text_run.py`（text）。**不要覆盖旧 lab 脚本与旧 runs**；新实验用新文件。

---

## 4. 碰到的问题与处理

### 4.1 单测全绿、页面却错

- **原因**：测试强制 `fixture` → 读 gold；页面走真 LLM。
- **处理**：分清「管道测试」与「准度评测」；准度用 gold / `eval_tool_gold` / prompt_lab / 真开票。

### 4.2 文本 PDF 仍出现港口拼写错误（如 NHAVA → NHAJA）

- **事实**：`pypdf` 文本层已是正确的 `NHAVA SHEVA`。
- **原因**：`LLM_INPUT_MODE=pdf` 让多模态模型再解一遍 PDF，字符识别不稳定。
- **处理**：可用 **vision** 稳住版面；有文字层时也可试 **html** / **html_mix**（拼写跟文字层坐标走）。

### 4.3 货代抬头 COASTING 串进业务字段（通知方 + 船名/航次）

样张上货代/出具方抬头和业务栏挤在一起；模型不稳定时会把抬头卷进 `notify_party` / `vessel` / `voyage`。

**处理**：

- Prompt：letterhead / 标题锚点 / staged ANALYSIS 先分块。
- **html**：坐标 HTML +「notify 只取同左栏」。
- **html_struct**：标题条右沿限制 notify；freight 同行、竖线右侧。
- **html_mix**：结构侧与 LLM 对照，不一致进 WARN 给人看。

### 4.4 为何不能「只喂纯文本」

- 平坦 `extract_text` 会破坏表格/栏位空间关系。
- 需要版面信息：页图（vision）、整 PDF（pdf），或**文字坐标 HTML**（html）。

### 4.5 「raw」名不副实

- 早期 `raw_extracted_data` 已经过 `_normalize_llm_fields`。
- **处理**：拆层——`llm_analysis` / `raw`（原样）/ `normalized` / `validated`。

### 4.6 脏数字被表单「洗掉」

- `2560OKGS` 若进 `<input type="number">` 会变空，校验再也看不到错误。
- **处理**：规则侧保留原文；UI 非规范数字用 text；校验信息带上原 token。

### 4.7 明确不做的优化

- 港口白名单 **模糊自动纠正**：关键字段用 WARN + 人工，不静默改写。
- 未知版式 **借用** `forwarder_export_so` 规则。

### 4.8 Agent 调 Tool 超时

- Agent→Tool 默认 `TOOL_HTTP_TIMEOUT_S=120`。`html_mix` + 慢文本模型可能超过 120s，页面表现为 upload 500（`httpx.ReadTimeout`），而 Tool 仍在等上游。
- Tool 单 worker：一次卡住会堵住后续解析。必要时加大超时并重启卡住的 Tool。

---

## 5. 调试与可观测

| 手段 | 说明 |
|------|------|
| 运行日志 | `logging` → 启动服务的终端 stdout（含 `form_family`、`mix_diff_fields`） |
| `PARSE_DEBUG_DUMP=true` | 写 `data/debug/parse_<时间>_<sid>.json`（含 pdf_text、analysis、raw、normalized、validated、report、`form_family`、`html_struct_raw`、`mix_diff_issues`） |
| 会话 meta | `form_family`、`html_struct_raw`、`mix_diff_fields` |
| vision + debug | 额外写页图路径到 dump |
| `DEBUG_DIR` | 默认 `data/debug`（已 gitignore） |

环境变量见 `.env.example`：`LLM_INPUT_MODE`、`OPENAI_MODEL`、`OPENAI_TEXT_MODEL`、`LLM_VISION_ZOOM`、`PARSE_DEBUG_DUMP`、`TOOL_HTTP_TIMEOUT_S` 等。

---

## 6. 当前推荐配置（实践结论）

按场景选模式，而不是死守一种：

| 场景 | 建议 |
|------|------|
| 有稳定文字层、要拼写准 + 可对照 | `LLM_INPUT_MODE=html_mix` + `OPENAI_TEXT_MODEL=glm-5.3`（或相当文本模型） |
| 仅规则、不调模型（已知版式） | `html_struct` |
| 扫描件 / 无可用文字层 | `vision` 或 `pdf` + `OPENAI_MODEL=glm-4.6v` |
| 离线单测 | `PARSE_BACKEND=fixture` |

默认代码 / `.env.example` 仍是 `LLM_INPUT_MODE=pdf`；本地演示可按上表改 `.env`（勿把含密钥的 `.env` 提交进仓）。

---

## 7. 待试 / backlog

- 更多版式家族（船司落货纸、十联单等）：有稳定样张与规则需求再加，禁止硬套货代 SO。
- 页图 + 文本层拼写约束的「vision 增强」（旧 backlog，与现有 `html_mix` 不同路径）。

---

## 8. 面试口述（约 40 秒）

> 托运单 PDF 结构化抽取在 Tool 侧完成，Agent 只调 Tool。输入模式可配：pdf/vision、文字坐标 html，以及不调模型的 html_struct。结构抽取先按运单版式分类，未知版式绝不套 BKG 规则。html_mix 用 LLM 做主结果，再用结构侧逐字段对照，不一致记 MIX-DIFF；脏数字保留原文，避免表单洗掉错误。冲突时规则和人工确认压过模型。

---

## 9. 相关文档与脚本

- 术语：`docs/glossary.md`
- 演示总览：`docs/demo_notes.md`、`docs/demo_pitch.md`
- Gold / 评测：`data/gold/`、`scripts/eval_accuracy.py`、`scripts/eval_tool_gold.py`
- Prompt 实验：`data/prompt_lab/README.md`
- 样张：`data/samples/`、`cn_shipping_orders/`、`web_shipping_orders/`
