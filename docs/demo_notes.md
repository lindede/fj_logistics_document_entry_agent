# 演示说明（M1–M3）

## 架构

```text
M-FE → Agent(:8000 Session+LangGraph) --HTTP Tool--> Tool(:8001 parse_booking)
                                              └─ M-PAR → M-VAL → M-MD
```

- 单进程：`APP_ROLE=all`（默认，测试用）
- 双进程：`APP_ROLE=tool` + `APP_ROLE=agent` 且 `TOOL_BASE_URL=http://127.0.0.1:8001`
- Tool：`POST /api/parse_booking`；MCP **风格**描述 `GET /api/mcp/tools`（非标准 MCP 协议）
- Agent：会话 API；开票 `parse` 节点只调 `invoke_parse_booking`（LangChain StructuredTool）
- `file_path`：本地相对/绝对路径，或 `http(s)` 远程 PDF

## 核心逻辑

1. 解析：多模态 LLM（PDF file_url / 页图）→ FLD key 补齐（缺省 `null`）
2. 校验：结构 + BR-01～06；报告 overall / issues / confidence
3. 网关：读报告分流 AwaitConfirm / AwaitHuman；提交为持久化节点
4. 工程边界：规则 > 人工 > LLM

## 准确率方案

- Gold：`data/gold/bkg_sample.json`
- 评测：`python scripts/eval_accuracy.py` → `docs/eval_baseline.md`
- 指标：字段级归一化 exact match；规则场景通过率
- 提准：标签对齐样例 PDF、少样本字段说明；VAL-07：开票落 `_pending/<sid>/source.pdf`，**仅人工改字段后再提交**晋升为 `feedback/<sid>/{source.pdf,gold.json}`

## 选做（M3）已落地

| 项 | 说明 |
| --- | --- |
| ADV-01 | 底栏自然语言改字段：LLM→`ui_patches` **只填表单**；须再点「保存并重验」才进图；无 key/fixture 时正则回退 |
| ADV-02 | `observe.timed` 记录耗时与字段置信度 |
| MCP | `/api/mcp/tools` + 共用 `parse_booking` |
| auto_on_pass | `POST /api/config/submit_strategy` |
| 换票冲突 | 进行中再上传会询问确认 |
| 编排 | LangGraph 最小图 + MemorySaver；说明见 `docs/flow_design.md` |

> **会话状态**：LangGraph 为唯一源；业务只认 `session_id`，在 `_cfg` 里等同 LangGraph `thread_id`。人机停在 `wait_human`（interrupt），改字段/提交/作废用 `Command(resume=…)`。
>
> **下一步 M4**（见 `docs/dev_plan.md`）：Agent 改为只调封装 Tool 门面；可先同进程验证，再可选拆成 Tool 服务 + Agent 服务。当前 Agent 仍直调 Python 解析/校验实现。
>
> **JSON Schema**：`data/schemas/booking_data.schema.json` 为字段单源；已用于 key 派生、`validate`（STRUCT-SCHEMA）、MCP `output_schema`、`GET /api/schemas/booking_data`（前端字段列表）。**HTTP `/api/parse_booking` 出参是否强制再校 schema 另议。**

## 待试（backlog）

- **混合解析**：页图看版面 + 文本层约束拼写（`vision` 已较稳，有空再试；纯 text 会毁表格关系）

解析全链路复盘（问题 / 改动 / 调试 / 面试口述）：见 [`docs/booking_parse_summary.md`](booking_parse_summary.md)。

## 启动

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_sample_pdf.py
uvicorn app.main:app --reload --port 8000
# 浏览器打开 http://127.0.0.1:8000
```
