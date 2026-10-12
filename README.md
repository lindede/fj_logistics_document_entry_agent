# 国际物流单证录入智能体（fj_logistics_document_entry_agent）

出口托运单（BKG）解析、业务校验与人机协同录入的 Demo 工程。

## 当前状态

以需求澄清与概要设计为主，代码实现按三里程碑推进（见开发计划）。

## 文档

| 文档 | 说明 |
| --- | --- |
| [docs/requirements_understanding.md](docs/requirements_understanding.md) | 需求理解对照 |
| [docs/module_design.md](docs/module_design.md) | 模块设计 |
| [docs/flow_design.md](docs/flow_design.md) | 流程 / 状态机 / Use Case |
| [docs/ui_design.md](docs/ui_design.md) | 前端架子（v4 Idle 模板） |
| [docs/dev_plan.md](docs/dev_plan.md) | 开发计划（M1～M3） |
| [docs/glossary.md](docs/glossary.md) | 术语表 |
| [docs/raw_requirements/](docs/raw_requirements/) | 原始需求 |

## 技术方向（约定）

- 后端：Python + FastAPI；解析默认 LLM（可配置）；校验独立可重入
- 前端：操作员工作台（顶进度 + 中区 + 底栏拖 PDF / 文字指令）
- 演示：核心链路可跑通即可，非完整产品

## 许可证

未指定（内部 Demo）。
