# 术语表

用于需求与实现交流时对齐说法。需求对照见 `docs/requirements_understanding.md`。

| 术语 | 英文/符号 | 含义 |
| --- | --- | --- |
| 托运单 / 订舱单 | BKG、Booking、Shipping Order | 出口货物托运类 PDF，本项目主输入样例 |
| 单证录入 | document entry | 从 PDF 抽取字段、校验并确认入库的过程 |
| 发货人 | shipper | 托运/出口方 |
| 收货人 | consignee | 收货方 |
| 通知方 | notify_party | 到港通知对象，常为货代 |
| 船名 | vessel | 承运船舶名称或船司简称（如样例中的 MSC） |
| 航次 | voyage | 该船某一航次编号；可空；**不做**白名单 |
| 装货港 | port_of_loading、POL | 起运港；港名与代码可写在同一字段 |
| 目的港 / 卸货港 | port_of_discharge、POD | 卸货港；同上 |
| 港口代码 | UN/LOCODE 等 | 如 CNTAO、INNSA；可与港名一并做港口白名单 |
| 箱型/箱量 | containers | 业务字段：`[{type, qty}]`，如 40HQ × 1（≠ BookingRecord） |
| 订舱业务数据 | BookingData | 一票托运单的业务字段快照（FLD-01～18） |
| 订舱记录 | BookingRecord | 一票会话的外层数据包：三件套 + meta + history + 状态（旧称「录入容器」） |
| 字段来源元数据 | meta | 各字段来源；默认 `llm`，人改后为 `human` 等 |
| 过程历史 | history | 本票解析/校验/编辑/提交等事件流水，便于追踪 |
| 件数 / 包装单位 | packages_qty / packages_unit | 如 160 CTNS |
| 品名 | goods_desc | 英文货名；原文表曾写 Cargo，统一用此 key |
| 毛重 / 重量单位 | gross_weight / weight_unit | 数值与单位分字段；阈值随单位变 |
| 体积 / 体积单位 | measurement / measurement_unit | 同上；单位如 CBM |
| 唛头 | marks | 箱唛；无证据为 `null`，不填 N/M |
| HS 编码 | hs_code | 海关商品归类码；无证据为 `null` |
| 运费条款 | freight | P 预付 / C 到付 / E 约定；无证据为 `null` |
| 原始提取数据 | raw_extracted_data | 刚抽出、未充分治理的结果 |
| 校验后数据 | validated_data | 清洗与规则处理后的可信数据 |
| 校验报告 | validation_report | 字段结果、置信度、建议操作 |
| 三件套 | — | 上三者合称；一次解析须齐套 |
| 分层校验 | validation layers | 标准化→结构→规则→人机/置信度→回归 |
| 业务规则 | BR-* | 确定性校验（如装港≠卸港、白名单） |
| 硬失败 | FAIL | 阻断或必须人工处理，不能当成功 |
| 警告 | WARN | 提示人工，默认可确认后继续 |
| 船名白名单 | vessel whitelist | 已知船名集合；未命中默认 WARN |
| 港口白名单 | port whitelist | 已知港名/代码；未命中默认 WARN |
| 校验网关 | validation gateway | Agent 读报告做分流，不是再跑一套检测 |
| 人工兜底 | human-in-the-loop | FAIL/低置信度时交操作员确认或修改 |
| 单据会话 | booking session | 一票单的开始/进行中/结束；同时仅一票 |
| 会话 ID | session_id | 一票唯一标识；**同时**作为 LangGraph `thread_id`（仅在 `_cfg` 映射）。禁止另维护第二套 ID |
| MCP Tool | Model Context Protocol Tool | 优先封装形态；可与 HTTP API 并存 |
| 解析接口 | `/api/parse_booking` | 解析+校验一体的 HTTP 形态 |
| 多模态 / 非结构化 | multimodal / unstructured | 版式不固定的文档；文本层优先，必要时 OCR/视觉 |
| 字段置信度 | field confidence | LLM 抽取路径上的字段分；用于日志/降级，不单独放行 |
| 工程边界 | — | 规则与结构裁决；冲突时：规则 > 人工 > LLM |
| 动态指令 | ADV-01 | 自然语言改已录入字段（如 KGS→TON），改后须再校验 |
| Demo / P0·P1·P2 | — | 可演示原型；优先级：必做 / 应做可简 / 选做 |
