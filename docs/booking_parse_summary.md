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

---

## 2. 当前数据流

```text
PDF
  ├─ pypdf 文本层 …… 单据门禁、调试对照、（未来）拼写约束
  └─ LLM 抽数（LLM_INPUT_MODE）
        pdf     = file_url 整份 PDF
        vision  = PyMuPDF 渲 PNG 页图（当前更稳）
        text    = 纯文本（丢版面，不推荐作主路径）
           │
           ├─ llm_analysis …… staged「### ANALYSIS」叙述
           ├─ raw_extracted_data …… 模型 JSON 原样（不做 normalize）
           ├─ normalized_data …… 约定规整（运费 P/C/E、唛头、航次等）
           └─ validate → validated_data + validation_report
```

关键代码：

| 环节 | 位置 |
|------|------|
| 抽数 / 模式切换 | `app/parse/extract.py` |
| 文本层 | `app/parse/pdf_io.py`（`pypdf`） |
| 页图 | `app/parse/pdf_pages.py`（PyMuPDF → PNG） |
| 解析+校验门面 | `app/booking/process.py` |
| 分层字段模型 | `app/models.py`（`BookingRecord`） |

---

## 3. 提示词策略

- 采用 **分阶段输出（v4）**：同一次回复内先 `### ANALYSIS`，再 `### JSON`。
- 字段必须与 ANALYSIS 对齐；规则含 voyage 不要带 ETD/电话、freight 规整为 P/C/E 等。
- `pdf` / `vision` **共用同一套规则**，仅开场白不同：
  - pdf：`下面直接给出完整……PDF`
  - vision：`下面是……页面图像（每页一张）`
- prompt 实验室：`data/prompt_lab/` + `scripts/prompt_lab_run.py`（迭代提示词用）。

---

## 4. 碰到的问题与处理

### 4.1 单测全绿、页面却错

- **原因**：测试强制 `fixture` → 读 gold；页面走真 LLM。
- **处理**：分清「管道测试」与「准度评测」；准度用 gold / `eval_tool_gold` / prompt_lab / 真开票。

### 4.2 文本 PDF 仍出现港口拼写错误（如 NHAVA → NHAJA）

- **事实**：`pypdf` 文本层已是正确的 `NHAVA SHEVA`。
- **原因**：`LLM_INPUT_MODE=pdf` 让多模态模型再解一遍 PDF，字符识别不稳定；prompt_lab 同 prompt 也可对可错。
- **处理**：改用 **vision**（自渲 PNG），实机体感明显更稳。

### 4.3 货代抬头 COASTING 串进业务字段（通知方 + 船名/航次）

样张上货代/出具方 **COASTING INT'L LOGISTICS** 的抬头（名址电话邮箱）和业务栏挤在一起；文本层里 Notify 还会和抬头字交错。模型不稳定时会把抬头内容「解释进」业务字段，两类都出现过：

**A. 通知方 `notify_party`**

- 正确应是业务栏里的通知人（如 `TENV INNOVATIONS…`）
- 错时把货代抬头 **COASTING…**（或抬头碎片）卷进 `notify_party`

**B. 船名 / 航次 `vessel` / `voyage`**

- 船名/航次栏原文常为 `BY MSC ETD:11-14`，旁侧又是 COASTING 联系信息
- 错时：`vessel` = `COASTING` / `BY MSC`（抬头或脏串当船名）；`voyage` 吃进 **ETD / 开航日 / 电话**

**处理（prompt 侧迭代，见 `data/prompt_lab/`）**：

- `v1_letterhead` / `explain`：抬头块 ≠ shipper / consignee / **notify_party** / vessel
- `v2_title_anchor`：用栏目标题锚定；`BY MSC ETD:…` 只取船司简称
- staged（v3/v4）：ANALYSIS 先分块区分「货代出具方」与当事人/船名航次，再出 JSON

即便如此，在 **pdf file_url** 下仍会偶发串台；**vision** 稳住版面后明显好转，但仍属已知风险点。

### 4.4 为何不能「只喂纯文本」

- 平坦 `extract_text` 会破坏表格/栏位空间关系（标签与值错位等）。
- 需要：**版面靠图，字符靠文本**（见 §7 待试混合模式）。

### 4.5 「raw」名不副实

- 早期 `raw_extracted_data` 已经过 `_normalize_llm_fields`，排错分不清模型 vs 后处理。
- **处理**：拆层——`llm_analysis` / `raw`（原样）/ `normalized` / `validated`；校验落在 normalize 之后。

### 4.6 明确不做的优化

- 港口白名单 **模糊自动纠正**（接近就改成标准港名）：关键字段业务风险高，用 WARN + 人工/强制提交，不静默改写。

### 4.7 上下文 128K vs 图片几百 KB

- 单位不同：128K 是 **token**；几百 KB 是 **文件字节**。
- 图像进模型会变成有限视觉 token，不是按字节 1:1 计入；两页 A4 @ zoom 2.5 通常远未顶满。

---

## 5. 调试与可观测

| 手段 | 说明 |
|------|------|
| 运行日志 | 无独立 log 文件；`logging` → 启动服务的终端 stdout |
| `PARSE_DEBUG_DUMP=true` | 每次 `process_booking` 写 `data/debug/parse_<时间>_<sid>.json`（含 pdf_text、analysis、raw、normalized、validated、report 等） |
| vision + debug | 额外写 `data/debug/vision_<时间>_z*/page_0x.png`，路径记在 dump 的 `vision_page_paths` |
| `DEBUG_DIR` | 默认 `data/debug`（已 gitignore） |

相关环境变量见 `.env.example`：`LLM_INPUT_MODE`、`LLM_VISION_ZOOM`、`PARSE_DEBUG_DUMP`、`OPENAI_MODEL`（高性能版 API id 为 `glm-4.6v`，无 `glm-4.6v-plus` 之名）。

---

## 6. 当前推荐配置（实践结论）

- **主路径**：`PARSE_BACKEND=llm` + `LLM_INPUT_MODE=vision`
- **模型**：`OPENAI_MODEL=glm-4.6v`（系列高性能版）
- **页图倍率**：`LLM_VISION_ZOOM=2.5`（清晰度与体积折中；可调 1.5～3）
- **PDF file_url**：保留作对照/回退，不再当作「更准」的默认
- **fixture**：仅离线单测

---

## 7. 待试：混合模式（有空再做）

**想法**：图看版面 + 文本层约束拼写。

- 同一次请求：页图（表格/栏位关系）+ `pypdf` 文本附录。
- Prompt 约定：布局看图；**具体拼写以文本层出现的字符串为准**（抑制视觉认错字）。
- 不是改回纯 `text` 模式；是在现有 vision 上增强。

状态：已记入 backlog，**有时间再试**。仓库内亦见 `docs/demo_notes.md`「待试」条目。

---

## 8. 面试口述（约 30 秒）

> 我们做托运单 PDF 结构化抽取。早期 PDF 直传多模态不稳定：一是重读认错港口字母，二是把货代抬头 COASTING 串进通知方或船名，航次还容易吃进 ETD/电话——用 letterhead / 分阶段 prompt 压过一轮。后来改成自渲页图的 vision，版面更稳；并把 raw / normalize / analysis 拆开便于排错。单测走 fixture 只保证管道。下一步计划试「图看版面 + 文本层约束拼写」的混合模式。

---

## 9. 相关文档与脚本

- 术语：`docs/glossary.md`
- 演示总览：`docs/demo_notes.md`
- Gold / 评测：`data/gold/`、`scripts/eval_accuracy.py`、`scripts/eval_tool_gold.py`
- Prompt 实验：`data/prompt_lab/README.md`
