# 评测基线（M2）

- 场景通过：`5/5`
- 字段准确率（相对 gold）：`1.0`

## 明细

```json
{
  "case_pass": "5/5",
  "field_accuracy": 1.0,
  "rows": [
    {
      "id": "gold_pass",
      "overall": "PASS",
      "accuracy": 1.0,
      "miss": [],
      "ok": true
    },
    {
      "id": "fail_same_ports",
      "overall": "FAIL",
      "ok": true
    },
    {
      "id": "not_booking",
      "overall": "FAIL",
      "ok": true
    },
    {
      "id": "warn_unknown_vessel",
      "overall": "WARN",
      "ok": true
    },
    {
      "id": "fail_weight_range",
      "overall": "FAIL",
      "ok": true
    }
  ],
  "notes": "baseline after heuristic extractor + few-shot labels in sample PDF"
}
```

## 提准记录

| 轮次 | 改动 | 字段准确率 |
| --- | --- | --- |
| R0 | 初版启发式标签抽取 | 见上 |
| R1 | 样例 PDF 标签对齐 + Cargo→goods_desc + 少数字段提示 | 期望 ≥ R0 |
