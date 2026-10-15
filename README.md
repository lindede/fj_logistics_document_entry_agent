# 国际物流单证录入智能体（fj_logistics_document_entry_agent）

出口托运单（BKG）解析、业务校验与人机协同录入 Demo（里程碑 M1–M3）。

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_sample_pdf.py
# 单进程（默认 APP_ROLE=all）
uvicorn app.main:app --reload --port 8000
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

### 双进程（Agent + Tool，推荐演示边界）

```bash
# 终端 1：Tool（默认 :8001）
./scripts/start_tool.sh

# 终端 2：Agent（默认 :8000，已设 TOOL_BASE_URL）
./scripts/start_agent.sh
```

启动脚本会 `source .env`。`PARSE_BACKEND` 以 `.env` 为准（示例为 `llm`）；离线联调可 `PARSE_BACKEND=fixture ./scripts/start_tool.sh`。亦可用 `TOOL_PORT` / `AGENT_PORT` / `TOOL_BASE_URL`。

金标测 Tool 抽取流（须 Tool 已起且多为 `llm`）：

```bash
python scripts/eval_tool_gold.py
# 或同进程：python scripts/eval_tool_gold.py --local
```

说明见 `data/gold/README.md`。

Agent 开票节点通过 LangChain `StructuredTool` / `invoke_parse_booking` 调 Tool，**不直连** `extract`。  
`file_path` 支持仓库相对路径、绝对路径、以及 `http(s)://` 远程 PDF。

样例 PDF：`data/samples/BKG.pdf`（从需求 Word 附件抽出的官方托运单）。

## 验收脚本

```bash
pytest -q
python scripts/run_e2e.py
python scripts/eval_accuracy.py
```

## 主要 API

交互式契约（OpenAPI，FastAPI 默认提供）：

- Agent：http://127.0.0.1:8000/docs （另有 `/redoc`、`/openapi.json`）
- Tool：http://127.0.0.1:8001/docs

| 接口 | 说明 |
| --- | --- |
| `POST /api/parse_booking` | 解析+校验，返回三件套（Tool；请求/响应见 `/docs`） |
| `GET /api/session` | 当前会话快照 |
| `POST /api/session/action` | 开票/改数/提交/作废/自然语言指令 |
| `POST /api/session/upload` | multipart 上传 PDF |
| `GET /api/mcp/tools` | MCP 风格 Tool 描述 |
| `POST /api/config/submit_strategy` | `manual` / `auto_on_pass` |

抽取主路径：`OPENAI_MODEL=glm-4.6v-flash` + `LLM_INPUT_MODE=pdf`（`file_url` **整份 PDF 直传**，多页不必拼成一张图）。  
失败时可回退 `vision`（每页一张图）。配置见 `.env.example`。

## 文档

| 文档 | 说明 |
| --- | --- |
| [docs/demo_pitch.md](docs/demo_pitch.md) | **现场演示主稿**（架构 / 核心逻辑 / 准确率） |
| [docs/test_cases.md](docs/test_cases.md) | 已实现测试用例（按分层治理对照） |
| [docs/dev_plan.md](docs/dev_plan.md) | 开发计划（M1–M4 现状） |
| [docs/demo_notes.md](docs/demo_notes.md) | 演示备忘（端口 / 选做速查） |
| [docs/eval_baseline.md](docs/eval_baseline.md) | 评测基线 |
| [docs/booking_parse_summary.md](docs/booking_parse_summary.md) | 解析链路复盘 |
| [docs/requirements_understanding.md](docs/requirements_understanding.md) | 需求对照 |
| [docs/module_design.md](docs/module_design.md) | 模块设计 |
| [docs/flow_design.md](docs/flow_design.md) | 流程与状态机 |
| [docs/ui_design.md](docs/ui_design.md) | UI 架子 |
| [data/gold/README.md](data/gold/README.md) | 金标与 Tool 用例说明 |

## 里程碑覆盖

- **M1**：FastAPI + 解析/校验/会话/工作台/提交持久化
- **M2**：BR-01～06、主数据、评测脚本与基线
- **M3**：Done 指令修正、可观测、MCP 风格、自动提交、换票询问
- **M4**：Tool / Agent 双服务边界（见 [docs/dev_plan.md](docs/dev_plan.md)）
