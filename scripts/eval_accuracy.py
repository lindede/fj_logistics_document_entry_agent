#!/usr/bin/env python3
"""字段级准确率与规则场景评测（M2）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.parse.extract import parse_pdf_bytes  # noqa: E402
from app.parse.schema_fill import fill_schema  # noqa: E402
from app.validate import validate_booking  # noqa: E402


def norm(v):
    if v is None:
        return None
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, str):
        return " ".join(v.upper().replace("–", "-").replace("—", "-").split())
    if isinstance(v, list):
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    return v


def field_score(pred: dict, gold: dict) -> tuple[int, int, list[str]]:
    keys = [k for k in gold.keys() if k != "voyage"]
    hit = 0
    miss = []
    for k in keys:
        if norm(pred.get(k)) == norm(gold.get(k)):
            hit += 1
        else:
            miss.append(k)
    return hit, len(keys), miss


def main() -> int:
    cases = json.loads((ROOT / "data/eval_cases/cases.json").read_text(encoding="utf-8"))
    total_hit = total_n = 0
    rows = []
    ok_cases = 0

    for case in cases:
        cid = case["id"]
        if case.get("inline"):
            raw = fill_schema(case["inline"])
            validated, report = validate_booking(raw, {})
            doc_ok = True
            pred = validated
        else:
            path = ROOT / case["file"]
            parsed = parse_pdf_bytes(path.read_bytes())
            doc_ok = parsed["doc_type_ok"]
            pred = parsed["raw_extracted_data"]
            validated, report = validate_booking(pred, parsed["field_confidence"])

        case_ok = True
        if "expect_doc_type_ok" in case and doc_ok != case["expect_doc_type_ok"]:
            case_ok = False
        if "expect_overall" in case and report.overall not in case["expect_overall"]:
            case_ok = False
        if "expect_rules" in case:
            rules = {i.rule for i in report.issues}
            if not set(case["expect_rules"]).issubset(rules):
                case_ok = False

        schema_fail = any(i.rule == "STRUCT-SCHEMA" for i in report.issues)
        if case.get("expect_schema_ok") is True and schema_fail:
            case_ok = False
        if case.get("expect_schema_ok") is False and not schema_fail:
            case_ok = False

        acc = None
        if case.get("gold"):
            gold = json.loads((ROOT / case["gold"]).read_text(encoding="utf-8"))
            hit, n, miss = field_score(pred, gold)
            total_hit += hit
            total_n += n
            acc = hit / n if n else 0
            rows.append(
                {
                    "id": cid,
                    "overall": report.overall,
                    "accuracy": round(acc, 4),
                    "miss": miss,
                    "schema_ok": not schema_fail,
                    "ok": case_ok,
                }
            )
        else:
            rows.append(
                {
                    "id": cid,
                    "overall": report.overall,
                    "schema_ok": not schema_fail,
                    "ok": case_ok,
                }
            )

        if case_ok:
            ok_cases += 1

    field_acc = total_hit / total_n if total_n else None
    out = {
        "case_pass": f"{ok_cases}/{len(cases)}",
        "field_accuracy": None if field_acc is None else round(field_acc, 4),
        "rows": rows,
        "notes": "baseline with multimodal LLM (or inline/fixture cases)",
    }
    out_path = ROOT / "docs" / "eval_baseline.md"
    md = [
        "# 评测基线（M2）",
        "",
        f"- 场景通过：`{out['case_pass']}`",
        f"- 字段准确率（相对 gold）：`{out['field_accuracy']}`",
        "",
        "## 明细",
        "",
        "```json",
        json.dumps(out, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 提准记录",
        "",
        "| 轮次 | 改动 | 字段准确率 |",
        "| --- | --- | --- |",
        "| R0 | 多模态 LLM 抽取基线 | 见上 |",
        "| R1 | 样例 PDF 标签对齐 + Cargo→goods_desc + 少数字段提示 | 期望 ≥ R0 |",
        "",
    ]
    out_path.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok_cases == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
