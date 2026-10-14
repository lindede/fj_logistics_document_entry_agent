# 金标与 Tool 用例

## 现在有多少 case？

见 `data/eval_cases/tool_gold_cases.json`，当前 **7** 条（2 正确 + 5 错误/告警）：

| kind | id | 作用 |
| --- | --- | --- |
| correct | `bkg_main` | 正确抽取（BKG.pdf → `bkg_sample.json`） |
| correct | `bkg_official` | 正确抽取（同源金标） |
| error_doc_type | `not_booking` | 错误：非托运单 PDF |
| error_doc_type | `not_booking_scan` | 错误：扫描非托运单（optional，门禁偶发漏） |
| error_rule | `fail_same_ports` | 错误：装港=卸港 → FAIL BR-01 + 字段金标 |
| error_rule | `warn_unknown_vessel_inline` | 警告：未知船名 → WARN BR-03 |
| error_rule | `fail_weight_range_inline` | 错误：毛重超范围 → FAIL BR-02 |

金标文件：

- `bkg_sample.json` — 正确主样例（notify=TENV）
- `bkg_fail_same_ports.json` — 合成失败单（POL=POD）
- `bkg_fail_no_notify.json` — 合成失败单（无通知方；PDF：`samples/BKG_fail_no_notify.pdf`）

扫描拆页等 PDF 尚未标金标，要加就补 `gold/*.json` + cases 一行。

## 怎么跑

```bash
# 全部（PDF 用例需 Tool llm 或 --local）
python scripts/eval_tool_gold.py --local

# 只跑错误类
python scripts/eval_tool_gold.py --local --kind error_rule
python scripts/eval_tool_gold.py --local --kind error_doc_type

# 只跑正确抽取（会打 LLM，较慢）
python scripts/eval_tool_gold.py --local --kind correct
```
