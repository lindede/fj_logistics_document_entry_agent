# 演示说明（M1–M4）

## 架构

```text
M-FE → Agent(:8000 Session+LangGraph) --HTTP Tool--> Tool(:8001 parse_booking)
                                              └─ M-PAR → M-VAL → M-MD
```

- 单进程：`APP_ROLE=all`（默认，测试用）
- 双进程：`APP_ROLE=tool` + `APP_ROLE=agent` 且 `TOOL_BASE_URL=http://127.0.0.1:8001`
- Tool：`POST /api/parse_booking`；MCP **风格**描述 `GET /api/mcp/tools`（非标准 MCP 协议）
- Agent：会话 API；开票 `parse` 节点只调 `invoke_parse_booking`（LangChain StructuredTool），**不直连** extract
- `file_path`：本地相对/绝对路径，或 `http(s)` 远程 PDF
- Agent→Tool 超时：`TOOL_HTTP_TIMEOUT_S`（默认 120）；`html_mix` + 慢模型可能需加大

## 核心逻辑

1. **解析**（`LLM_INPUT_MODE`）：`pdf` / `vision` / `text` / `html` / `html_struct` / `html_mix` → FLD key 补齐（缺省 `null`）
2. **版式**（struct / mix）：`struct_forms` 先分类；`forwarder_export_so` 有规则；`unknown` 不套用
3. **校验**：结构 + BR-01～06；`html_mix` 另附 `MIX-DIFF` / `MIX-FORM`；报告 overall / issues / confidence
4. **网关**：读报告分流 AwaitConfirm / AwaitHuman；提交为持久化节点
5. **工程边界**：规则 > 人工 > LLM

## 准确率方案

- Gold：`data/gold/bkg_sample.json`
- 评测：`python scripts/eval_accuracy.py` → `docs/eval_baseline.md`
- 指标：字段级归一化 exact match；规则场景通过率
- 提准：标签对齐样例 PDF；`html`/`html_mix` 用文字坐标；规则侧与 LLM 对照；VAL-07：开票落 `_pending/<sid>/source.pdf`，**仅人工改字段后再提交**晋升为 `feedback/<sid>/{source.pdf,gold.json}`

## 选做（M3）已落地

| 项 | 说明 |
| --- | --- |
| ADV-01 | **Done 态**底栏指令：LLM Function Calling → `amend_booking_record`（先验后写 store）；FAIL 不落盘；UI 高亮变更/错误字段；Await 用表单，不再 NL 填表 |
| ADV-02 | `observe.timed` 记录耗时与字段置信度 |
| MCP | `/api/mcp/tools` + 共用 `parse_booking` |
| auto_on_pass | `POST /api/config/submit_strategy` |
| 换票冲突 | 进行中再上传会询问确认 |
| 编排 | LangGraph 最小图 + MemorySaver；说明见 `docs/flow_design.md` |

> **会话状态**：LangGraph 为唯一源；业务只认 `session_id`，在 `_cfg` 里等同 LangGraph `thread_id`。人机停在 `wait_human`（interrupt），改字段/提交/作废用 `Command(resume=…)`。
>
> **M4 已完成**：Agent 只调 Tool 门面；双进程用 `start_tool.sh` / `start_agent.sh`。
>
> **JSON Schema**：`data/schemas/booking_data.schema.json` 为字段单源；已用于 key 派生、`validate`（STRUCT-SCHEMA）、MCP `output_schema`、`GET /api/schemas/booking_data`（前端字段列表）。

## 解析模式速查

| `LLM_INPUT_MODE` | 何时用 |
| --- | --- |
| `html_mix` | 有文字层、要 LLM 主结果 + 结构对照（推荐演示） |
| `html_struct` | 已知货代 SO 版式、不调模型 |
| `html` | 只要坐标 HTML + 文本模型 |
| `vision` / `pdf` | 扫描件或无可靠文字层 |
| `text` | 仅对照实验，不作主路径 |

配置与坑点见 [`docs/booking_parse_summary.md`](booking_parse_summary.md)。

## Backlog（非阻塞）

- 更多运单版式家族（船司落货纸等）
- vision + 文本层拼写约束（与 `html_mix` 不同路径）
- flow_design 全文与 Done 态对齐

## 启动

```bash
# 双进程演示
./scripts/start_tool.sh    # :8001
./scripts/start_agent.sh   # :8000 → http://127.0.0.1:8000

# 或单进程
uvicorn app.main:app --reload --port 8000
```
