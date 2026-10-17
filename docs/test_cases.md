# 已实现测试用例

按分层治理对照整理（与 [demo_pitch.md](demo_pitch.md) §2.3 对应）。  
跑单元/集成：`pytest -q`。金标评测见 [data/gold/README.md](../data/gold/README.md)、[eval_baseline.md](eval_baseline.md)。

当前 pytest 收集：**74** 条（以 `pytest --collect-only -q` 为准）。

---

## 1. 输入标准化

| 用例 | 文件 | 说明 |
|------|------|------|
| `test_normalize_text_nfkc_and_space` | [tests/test_normalize.py](../tests/test_normalize.py) | 文本 NFKC / 空白 |
| `test_normalize_extracted_text_fields` | 同上 | 抽数字段规整 |
| `test_fill_schema_runs_normalize_then_coerce` | 同上 | 规整后再 coerce |
| `test_normalize_freight_aliases` | [tests/test_freight_normalize.py](../tests/test_freight_normalize.py) | 运费写法 → P/C/E |
| `test_normalize_llm_fields_maps_freight` | 同上 | LLM 字段映射运费 |
| `test_fixture_parse_separates_raw_and_normalized` | 同上 | raw 与 normalized 分离 |
| `test_relative_local_path` / `absolute` / `missing` | [tests/test_pdf_io_paths.py](../tests/test_pdf_io_paths.py) | 本地 PDF 路径 |
| `test_remote_http_url` / `test_remote_too_large` | 同上 | 远程 PDF |
| `test_split_keeps_stray_letters` | [tests/test_html_struct.py](../tests/test_html_struct.py) | `2560OKGS` 不拆掉 O |
| `test_dirty_weight_stays_visible_as_failure` | 同上 | 脏毛重进校验文案 |
| `test_split_exact_number_and_known_unit` | 同上 | `25600KGS` / `160CTNS` 可拆 |
| `test_bare_number_uses_header_unit_only` | 同上 | 裸数字只用表头单位 |

---

## 2. 结构化输出

| 用例 | 文件 | 说明 |
|------|------|------|
| `test_keys_derived_from_json_schema` | [tests/test_config_schema_keys.py](../tests/test_config_schema_keys.py) | 字段 key 来自 Schema |
| `test_schema_ok_on_base` / `rejects_non_int_packages` | [tests/test_schema_check.py](../tests/test_schema_check.py) | Schema 校验 |
| `test_validate_booking_includes_schema` | 同上 | 校验含 STRUCT-SCHEMA |
| `test_coerce_numeric_strings` 等 | [tests/test_schema_fill.py](../tests/test_schema_fill.py) | 补齐 / 数值 coerce；非数字不强制 |
| `test_parse_pure_json` / staged / code_fence | [tests/test_extract_staged_parse.py](../tests/test_extract_staged_parse.py) | 分阶段 LLM 输出解析 |
| `test_parse_llm_response_keeps_raw_unnormalized` | 同上 | raw 不被 normalize 污染 |
| `test_validated_data_*_roundtrip` | [tests/test_booking_record_roundtrip.py](../tests/test_booking_record_roundtrip.py) | BookingRecord 往返不丢字段 |
| `test_sanitize_drops_unknown_keys` | [tests/test_nl_patch.py](../tests/test_nl_patch.py) | 非法 key 丢弃 |
| `test_bkg_html_struct_matches_fields` | [tests/test_html_struct.py](../tests/test_html_struct.py) | BKG 规则抽取对金标（货名可含中文） |
| `test_parse_pdf_bytes_html_struct_skips_llm` | 同上 | html_struct 不要求 API key |
| `test_bkg_is_forwarder_export_so` | [tests/test_html_mix.py](../tests/test_html_mix.py) | BKG → `forwarder_export_so` |
| `test_unrecognized_form_does_not_use_forwarder_rules` | 同上 | 未知版式 fields={}；struct 抛错 |
| `test_html_mix_uses_llm_primary_and_flags_goods_desc` | 同上 | mix 主结果用 LLM；货名不一致 MIX-DIFF |
| `test_html_mix_llm_failure_does_not_fall_back_to_struct` | 同上 | LLM 失败不回退 struct |
| `test_html_mix_unknown_form_warns_without_field_diffs` | 同上 | 未知版式单条 MIX-FORM |
| `test_field_values_equal_voyage_and_empty` / `mix_diff_issues_message_*` | 同上 | 对照相等与文案 |

---

## 3. 业务规则

| 用例 | 文件 | 说明 |
|------|------|------|
| `test_br01_fail` | [tests/test_validate.py](../tests/test_validate.py) | 装港=卸港 → FAIL |
| `test_br02_fail` | 同上 | 毛重超范围 → FAIL |
| `test_br02_weight_scales_with_container_qty` | 同上 | 毛重阈值随箱量 |
| `test_br02_measurement_by_container_type` | 同上 | 体积按箱型 |
| `test_br03_warn` | 同上 | 未知船名 → WARN |
| `test_br04_warn` | 同上 | shipper==consignee 等 WARN |
| `test_pass_sample_like` | 同上 | 样例级 PASS |
| `test_process_booking_returns_record` | [tests/test_booking_process.py](../tests/test_booking_process.py) | 门面出 BookingRecord |
| `test_triple_projected_from_record` | 同上 | 三件套投影 |
| `test_parse_booking_sample` | [tests/test_api.py](../tests/test_api.py) | HTTP 解析样例 |
| `test_process_booking_merges_mix_diff_as_warn` | [tests/test_html_mix.py](../tests/test_html_mix.py) | MIX-DIFF 并入报告；PASS→WARN |
| `test_struct_alone_matches_gold_ports` | 同上 | 纯 struct 港口/通知方对齐金标 |

评测场景（非 pytest，脚本）：

| id | 来源 | 期望 |
|----|------|------|
| `gold_pass` | [data/eval_cases/cases.json](../data/eval_cases/cases.json) | PASS + 字段准 |
| `fail_same_ports` | 同上 | FAIL |
| `not_booking` | 同上 | FAIL（非托运单） |
| `warn_unknown_vessel` | 同上 | WARN |
| `fail_weight_range` | 同上 | FAIL |

Tool 金标（[tool_gold_cases.json](../data/eval_cases/tool_gold_cases.json)，详见 [gold/README](../data/gold/README.md)）：`bkg_main`、`bkg_official`、`not_booking`、`fail_same_ports`、`warn_unknown_vessel_inline`、`fail_weight_range_inline` 等。

---

## 4. 人机 + 置信度

| 用例 | 文件 | 说明 |
|------|------|------|
| `test_open_stops_at_wait_human` | [tests/test_graph.py](../tests/test_graph.py) | 开票停在等人 |
| `test_session_open_uses_graph_session` | 同上 | session = graph thread |
| `test_patch_resume_same_session` | 同上 | 改字段 resume 同会话 |
| `test_submit_resume_ends_wait` | 同上 | 提交结束等待 |
| `test_submit_blocks_fail_unless_force` | [tests/test_force_submit.py](../tests/test_force_submit.py) | FAIL 普通提交拒绝 / 强制可过 |
| `test_submit_blocks_warn_unless_force` | 同上 | WARN 同上 |
| `test_session_flow_void` | [tests/test_api.py](../tests/test_api.py) | 会话作废 |
| `test_amend_writes_only_on_pass` | [tests/test_amend.py](../tests/test_amend.py) | Done 修正仅非 FAIL 写盘 |
| `test_amend_rejects_fail_without_write` | 同上 | FAIL 不落盘 |
| `test_session_done_chat_amends` | 同上 | Done 底栏指令修正 |
| `test_await_chat_nl_rejected` | 同上 | Await 文字修正拒绝 |
| `test_chat_nl_in_await_does_not_apply_ui_only` | [tests/test_nl_ui_only.py](../tests/test_nl_ui_only.py) | Await 不再 NL 填表 |
| `test_regex_fallback_kgs_to_ton` | [tests/test_nl_patch.py](../tests/test_nl_patch.py) | NL 正则回退 KGS→TON |

---

## 5. 持续评估

| 用例 | 文件 | 说明 |
|------|------|------|
| `test_pending_source_saved_on_open` | [tests/test_feedback.py](../tests/test_feedback.py) | 开票落 pending PDF |
| `test_submit_without_human_discards_pending` | 同上 | 无人改不晋升 |
| `test_submit_after_human_patch_promotes` | 同上 | 人改后再提交 → 回归用例 |
| `test_void_discards_pending` | 同上 | 作废丢 pending |
| `test_promote_or_discard_unit` | 同上 | 晋升/丢弃单元 |

脚本：

| 命令 | 说明 |
|------|------|
| `python scripts/eval_accuracy.py` | 字段/场景准确率 → [eval_baseline.md](eval_baseline.md) |
| `python scripts/eval_tool_gold.py` | Tool 金标流 |
| `python scripts/run_e2e.py` | 端到端脚本 |

---

## 6. Tool / Agent 边界（横切）

| 用例 | 文件 | 说明 |
|------|------|------|
| `test_local_invoke_parse_booking` | [tests/test_parse_booking_tool.py](../tests/test_parse_booking_tool.py) | 本地门面 |
| `test_agent_role_requires_tool_url` | 同上 | Agent 角色须 Tool URL |
| `test_http_invoke` | 同上 | HTTP 调 Tool |
| `test_langchain_structured_tool` | 同上 | StructuredTool 封装 |
| `test_health` / `test_mcp_tools` | [tests/test_api.py](../tests/test_api.py) | 健康检查 / MCP 描述 |

---

## 怎么跑

```bash
pytest -q
pytest tests/test_html_struct.py tests/test_html_mix.py -q
pytest tests/test_validate.py tests/test_force_submit.py tests/test_amend.py -q
python scripts/eval_accuracy.py
python scripts/eval_tool_gold.py --local
```
