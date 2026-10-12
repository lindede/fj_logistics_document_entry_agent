# 演示说明（M1–M3）

## 架构

```text
M-FE(工作台) → M-AGT(会话) → M-PAR(解析) → M-VAL(校验) → M-MD(主数据)
                ↑                ↑
              M-GW(/api)      M-OBS(日志耗时/置信度)
```

- HTTP：`POST /api/parse_booking`（三件套）
- MCP 风格：`GET /api/mcp/tools` 描述 Tool，核心与 HTTP 共用
- 会话：`/api/session`、`/api/session/action`、`/api/session/upload`

## 核心逻辑

1. 解析：PDF 文本层 → 启发式/可选 LLM → FLD key 补齐（缺省 `null`）
2. 校验：结构 + BR-01～06；报告 overall / issues / confidence
3. 网关：读报告分流 AwaitConfirm / AwaitHuman；提交为持久化节点
4. 工程边界：规则 > 人工 > LLM

## 准确率方案

- Gold：`data/gold/bkg_sample.json`
- 评测：`python scripts/eval_accuracy.py` → `docs/eval_baseline.md`
- 指标：字段级归一化 exact match；规则场景通过率
- 提准：标签对齐样例 PDF、少样本字段说明；VAL-07 回流目录 `data/feedback/`（占位）

## 选做（M3）已落地

| 项 | 说明 |
| --- | --- |
| ADV-01 | 底栏自然语言改单位（KGS→TON）后重验 |
| ADV-02 | `observe.timed` 记录耗时与字段置信度 |
| MCP | `/api/mcp/tools` + 共用 `parse_booking` |
| auto_on_pass | `POST /api/config/submit_strategy` |
| 换票冲突 | 进行中再上传会询问确认 |
| 编排说明 | 见 `docs/flow_design.md`（等价 LangGraph 节点） |

## 启动

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_sample_pdf.py
uvicorn app.main:app --reload --port 8000
# 浏览器打开 http://127.0.0.1:8000
```
