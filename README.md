# 国际物流单证录入智能体（fj_logistics_document_entry_agent）

出口托运单（BKG）解析、业务校验与人机协同录入 Demo（里程碑 M1–M3）。

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_sample_pdf.py
uvicorn app.main:app --reload --port 8000
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

样例 PDF：`data/samples/BKG.pdf`（从需求 Word 附件 `oleObject1.bin` 抽出的官方托运单；合成标签版留作 `BKG_synthetic_labeled.pdf`）。

## 验收脚本

```bash
pytest -q
python scripts/run_e2e.py
python scripts/eval_accuracy.py
```

## 主要 API

| 接口 | 说明 |
| --- | --- |
| `POST /api/parse_booking` | 解析+校验，返回三件套 |
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
| [docs/dev_plan.md](docs/dev_plan.md) | 开发计划 |
| [docs/demo_notes.md](docs/demo_notes.md) | 演示架构 / 准确率 / 选做 |
| [docs/eval_baseline.md](docs/eval_baseline.md) | 评测基线（跑评测脚本后生成） |
| [docs/requirements_understanding.md](docs/requirements_understanding.md) | 需求对照 |
| [docs/module_design.md](docs/module_design.md) | 模块设计 |
| [docs/flow_design.md](docs/flow_design.md) | 流程与状态机 |
| [docs/ui_design.md](docs/ui_design.md) | UI 架子 |

## 里程碑覆盖

- **M1**：FastAPI + 解析/校验/会话/工作台/提交持久化
- **M2**：BR-01～06、主数据、评测脚本与基线
- **M3**：动态指令、可观测日志、MCP 描述、自动提交开关、换票询问
