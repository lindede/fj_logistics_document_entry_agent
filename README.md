# 国际物流单证录入智能体（fj_logistics_document_entry_agent）

出口托运单（BKG）解析、业务校验与人机协同录入 Demo（里程碑 M1–M4）。

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

启动脚本会 `source .env`。`PARSE_BACKEND` / `LLM_INPUT_MODE` 以 `.env` 为准（`.env.example` 演示默认：`llm` + `html_mix`）；离线联调可 `PARSE_BACKEND=fixture ./scripts/start_tool.sh`。亦可用 `TOOL_PORT` / `AGENT_PORT` / `TOOL_BASE_URL`。uvicorn `--reload` **不**监视 `.env`，改模式后需重启服务。复制 `.env.example` 时只填本地 `OPENAI_API_KEY`，勿把密钥提交进仓。

金标测 Tool 抽取流（须 Tool 已起且多为 `llm`）：

```bash
python scripts/eval_tool_gold.py
# 或同进程：python scripts/eval_tool_gold.py --local
```

说明见 `data/gold/README.md`。

Agent 开票节点通过 LangChain `StructuredTool` / `invoke_parse_booking` 调 Tool，**不直连** `extract`。  
`file_path` 支持仓库相对路径、绝对路径、以及 `http(s)://` 远程 PDF。

## 解析模式（`LLM_INPUT_MODE`）

| 模式 | 说明 |
| --- | --- |
| `html_mix` | **演示默认**；先结构抽取再 html LLM；主结果用 LLM，不一致记 `MIX-DIFF`；未知版式记 `MIX-FORM` |
| `html` | 文字坐标 HTML + `OPENAI_TEXT_MODEL`（需文字层） |
| `html_struct` | 版式分类 + 坐标/矩形规则，**不调大模型**（别名 `xtml_struct`） |
| `pdf` | 多模态 `file_url` 直传 PDF（未设环境变量时的代码兜底） |
| `vision` | 每页渲成 PNG 再传视觉模型 |
| `text` | 纯文本 + 文本模型（丢版面） |

规则抽取按运单**版式家族**分派（当前实现 `forwarder_export_so`；未知不套用 BKG 规则）。详见 [docs/booking_parse_summary.md](docs/booking_parse_summary.md)。

视觉模型：`OPENAI_MODEL`（如 `glm-4.6v`）。文本 / html：`OPENAI_TEXT_MODEL`。完整变量见 `.env.example`。

## 样例 PDF

| 路径 | 说明 |
| --- | --- |
| `data/samples/BKG.pdf` | 主金标托运单（货代出口 SO 版式） |
| `data/samples/cn_shipping_orders/` | 中文落货纸/托运单教学样张 |
| `data/samples/web_shipping_orders/` | 公开空白模板 + 本地生成填单 |

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

## 文档

| 文档 | 说明 |
| --- | --- |
| [docs/demo_pitch.md](docs/demo_pitch.md) | **现场演示主稿**（架构 / 核心逻辑 / 准确率） |
| [docs/test_cases.md](docs/test_cases.md) | 已实现测试用例（按分层治理对照） |
| [docs/dev_plan.md](docs/dev_plan.md) | 开发计划（M1–M4 现状） |
| [docs/demo_notes.md](docs/demo_notes.md) | 演示备忘（端口 / 选做速查） |
| [docs/eval_baseline.md](docs/eval_baseline.md) | 评测基线 |
| [docs/booking_parse_summary.md](docs/booking_parse_summary.md) | **解析链路复盘**（模式 / 版式 / mix） |
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
