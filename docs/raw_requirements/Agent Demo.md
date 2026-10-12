# 国际物流单证录入智能体原型设计

## 1. 背景设定

我们是国际物流公司。操作人员每天收到大量邮件，类似 **BKG.pdf** 的出口货物托运单。

我们需要一个 **“单证录入智能体原型”**，它能读取该 PDF 内容，**自动提取关键信息**，并进行 **业务校验**，最终以 **HTML / Vue 页面** 的形式展现解析与校验结果。

## 2. 核心要求（必做项）

请使用 **Python + FastAPI** 完成以下任务：

### 1) 多模态/非结构化数据解析

读取 BKG.pdf 文件，提取以下字段并输出结构化的 JSON。

#### 必填字段（源数据中有直接对应关系）

| 序号 | 字段名（JSON Key） | 说明 | 样例值 |
| --- | --- | --- | --- |
| 1 | shipper | 发货人 | Guangzhou Great Power Energy (Qingdao) Co., Ltd. |
| 2 | consignee | 收货人 | GREAT POWER NEW ENERGY CO., LTD |
| 3 | notify_party | 通知方 | COASTING INT'L LOGISTICS CO., LTD. |
| 4 | vessel | 船名 | MSC |
| 5 | voyage | 航次 | 若提取不到可为空字符串 |
| 6 | port_of_loading | 装货港 | QINGDAO –CNTAO |
| 7 | port_of_discharge | 目的港 | NHAVA SHEVA -- INNSA |
| 8 | containers | 箱型/箱量 | [{"type": "40HQ", "qty": 1}] |
| 9 | packages_qty | 件数（纯数字） | 160 |
| 10 | packages_unit | 包装单位 | CTNS |
| 11 | Cargo | 品名(英文) | Rechargeable Li-ion Cell |
| 12 | gross_weight | 毛重（纯数字） | 25600 |
| 13 | weight_unit | 重量单位 | KGS |
| 14 | measurement | 体积（纯数字） | 32.03 |
| 15 | measurement_unit | 体积单位 | CBM |

#### 扩展字段（若源数据中无直接对应，留空即可）

| 序号 | 字段名 | 说明 |
| --- | --- | --- |
| 16 | hs_code | HS CODE（可为空） |
| 17 | marks | 唛头（可为空） |
| 18 | freight | 付费方式（P/C/E，可为空） |

#### 期望格式

```json
{
  "shipper": "string",
  "consignee": "string",
  "notify_party": "string",
  "vessel": "string",
  "voyage": "string",
  "port_of_loading": "string",
  "port_of_discharge": "string",
  "containers": [{"type": "string", "qty": "integer"}],
  "packages_qty": "integer",
  "packages_unit": "string",
  "goods_desc": "string",
  "gross_weight": "number",
  "weight_unit": "string",
  "measurement": "number",
  "measurement_unit": "string",
  "hs_code": "string",
  "marks": "string",
  "freight": "string"
}
```

### 2) 业务规则校验与数据治理

物流单证录入对数据准确性要求极高，绝不允许编造或错误录入。请针对提取的数据，设计一套 **分层校验与治理**，至少包含以下标准层次：

1. **输入验证与标准化层**：说明如何清洗 OCR/PDF 提取的原始文本，统一字符编码与格式；
2. **结构化输出控制层**：说明如何确保 LLM 或解析模块输出符合固定 JSON；
3. **业务规则引擎校验层**：至少实现 **3 条** 确定性校验规则（逻辑勾稽、阈值判断、跨字段比对）；
4. **人机协同与置信度评估层**：说明当校验不通过或置信度低于阈值时，系统如何优雅降级并触发人工介入；
5. **持续评估与回归测试机制**：说明如何将人工修正的 bad case 自动转化为测试用例，防止准确率回退。

最终输出应包含：

- `raw_extracted_data`（原始提取数据）
- `validated_data`（经校验清洗后的可信数据）
- `validation_report`（校验报告，包含字段级校验结果、置信度评分、建议操作）

### 3) MCP 工具化封装（若不了解 MCP，也可以封装普通 API）

- 将上述解析 + 校验能力封装为一个 **MCP 风格的 Tool**（即一个独立的 API 接口 `/api/parse_booking`）。
- 入参：`file_path` 或 `base64_pdf`。
- 出参：包含原始提取数据、标准化校验数据、校验报告。

### 4) Agent 工作流编排设计（输出设计图/文本描述）

请用文字 + 流程图描述：如果你将上述 Tool 交给 LLM Agent（如：LangGraph），如何设计一个“人机协同”的工作流？

主要内容包括：

- 场景：Agent 执行后发现 FAIL（比如毛重缺失），Agent 是直接拒绝？还是反问操作员？还是去查询历史数据补全？
- 请画出 **状态** 或 **节点流转图**（意图识别 → 工具调用 → 校验网关 → 人工兜底）。
- 设计原则说明（确定与 LLM 概率的工程边界，如果发生冲突时如何处理）。

## 3. 进阶挑战（选做）

- **A. 动态指令遵循**：操作员可能说“帮我把毛重单位从 KGS 换成 TON”。请展示如何通过自然语言修改已录入的数据（体现 Function Calling 的修改逻辑）。
- **B. 可观测性埋点**：为上述 API 增加一个简单的日志装饰器，记录每次调用提取的 **耗时** 和 **字段置信度**（如果使用了 LLM 提取的话）。

## 现场演示要求

1. 从收到试题之日起，7 个工作日内完成 Demo 制作。
2. 完成后随时与人力联系，预约现场演示时间。
3. 请自带笔记本电脑，提前配置好运行环境（Python 虚拟环境、依赖已安装、测试文件已放入工程目录）。
4. 请准备一份 **PPT / Markdown 文稿**（不限格式，主要包括：架构设计图、核心逻辑说明、准确率提升方案），**可运行的原型**（**不必是完整产品，但核心链路需可演示**）。
