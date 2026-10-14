#!/usr/bin/env python3
"""用金标/期望测 Tool 流：正确抽取 + 错误单据/规则失败。

HTTP /api/parse_booking 或 --local process_booking；
inline 用例不经 PDF，只跑 validate_booking（校验层）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES_PATH = ROOT / "data" / "eval_cases" / "tool_gold_cases.json"


def norm(v):
    if v is None:
        return None
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, str):
        s = " ".join(v.upper().replace("–", "-").replace("—", "-").split())
        s = s.replace("'", "").replace("’", "").replace("`", "")
        if s in {"N/M", "NM", "N.M", ""}:
            return None
        return s
    if isinstance(v, list):
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    return v


def field_equal(key: str, pred, gold) -> bool:
    if key == "goods_desc":
        p = norm(pred) or ""
        g = norm(gold) or ""
        if not g:
            return not p
        return g in p or p in g
    if key == "voyage":
        p = pred if pred is not None else ""
        g = gold if gold is not None else ""
        if norm(g) in (None, ""):
            ps = str(p)
            if re.search(r"ETD|\d{5,}", ps, re.I):
                return False
            return norm(p) in (None, "")
        return norm(p) == norm(g)
    return norm(pred) == norm(gold)


def score(pred: dict, gold: dict) -> tuple[int, int, list[str]]:
    keys = list(gold.keys())
    hit = 0
    miss = []
    for k in keys:
        if field_equal(k, pred.get(k), gold.get(k)):
            hit += 1
        else:
            miss.append(f"{k}: pred={pred.get(k)!r} gold={gold.get(k)!r}")
    return hit, len(keys), miss


def report_rules(report: dict) -> set[str]:
    issues = report.get("issues") or []
    return {str(i.get("rule")) for i in issues if isinstance(i, dict) and i.get("rule")}


def call_tool_http(tool_url: str, pdf_path: Path) -> dict:
    import httpx

    body = {"file_path": str(pdf_path.resolve())}
    with httpx.Client(timeout=300.0, trust_env=False) as client:
        r = client.post(f"{tool_url.rstrip('/')}/api/parse_booking", json=body)
        r.raise_for_status()
        return r.json()


def call_local(pdf_path: Path) -> dict:
    from app.booking import process_booking, triple_from_record

    rec = process_booking(file_path=str(pdf_path.resolve()))
    return triple_from_record(rec)


def call_inline(data: dict) -> dict:
    from app.parse.schema_fill import fill_schema
    from app.validate import validate_booking

    raw = fill_schema(data)
    validated, report = validate_booking(raw, {})
    return {
        "doc_type_ok": True,
        "raw_extracted_data": raw,
        "validated_data": validated,
        "validation_report": report.model_dump()
        if hasattr(report, "model_dump")
        else report.dict(),
    }


def eval_expectations(case: dict, out: dict) -> tuple[bool, dict]:
    """综合 doc_type / gold / overall / rules。"""
    detail: dict = {"id": case["id"], "kind": case.get("kind")}
    ok = True
    doc_ok = out.get("doc_type_ok", True)
    report = out.get("validation_report") or {}
    overall = report.get("overall")
    pred = (
        out.get("validated_data")
        or out.get("normalized_data")
        or out.get("raw_extracted_data")
        or {}
    )

    if "expect_doc_type_ok" in case:
        got = bool(doc_ok) == bool(case["expect_doc_type_ok"])
        detail["doc_type_ok"] = doc_ok
        detail["expect_doc_type_ok"] = case["expect_doc_type_ok"]
        if not got:
            ok = False

    if case.get("gold"):
        gold = json.loads((ROOT / case["gold"]).read_text(encoding="utf-8"))
        hit, n, miss = score(pred, gold)
        detail["accuracy"] = round(hit / n, 4) if n else 0.0
        detail["hit"] = hit
        detail["n"] = n
        detail["miss"] = miss
        if hit != n:
            ok = False

    if case.get("expect_overall"):
        detail["overall"] = overall
        detail["expect_overall"] = case["expect_overall"]
        if overall not in case["expect_overall"]:
            ok = False

    if case.get("expect_rules"):
        rules = report_rules(report)
        detail["rules"] = sorted(rules)
        detail["expect_rules"] = case["expect_rules"]
        if not set(case["expect_rules"]).issubset(rules):
            ok = False

    detail["ok"] = ok
    return ok, detail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gold/error eval against Tool flow")
    ap.add_argument("--tool-url", default="http://127.0.0.1:8001")
    ap.add_argument("--local", action="store_true", help="不经 HTTP，直调 process_booking")
    ap.add_argument("--cases", type=Path, default=CASES_PATH)
    ap.add_argument(
        "--kind",
        default="",
        help="只跑某类：correct / error_doc_type / error_rule（空=全部）",
    )
    args = ap.parse_args(argv)

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.kind.strip():
        kind = args.kind.strip()
        cases = [c for c in cases if c.get("kind") == kind]

    rows = []
    all_ok = True

    for case in cases:
        cid = case["id"]
        kind = case.get("kind", "")
        print(f"→ {cid} [{kind}] …", flush=True)

        try:
            if case.get("inline") is not None:
                out = call_inline(case["inline"])
            else:
                pdf = ROOT / case["file"]
                if not pdf.is_file():
                    raise FileNotFoundError(pdf)
                if args.local:
                    out = call_local(pdf)
                else:
                    out = call_tool_http(args.tool_url, pdf)
        except Exception as exc:
            rows.append({"id": cid, "kind": kind, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            all_ok = False
            print(f"  ERR {exc}", flush=True)
            continue

        ok, detail = eval_expectations(case, out)
        detail["optional"] = bool(case.get("optional"))
        if not ok and not case.get("optional"):
            all_ok = False
        rows.append(detail)
        label = "PASS" if ok else ("SOFT-FAIL" if case.get("optional") else "FAIL")
        bits = [label]
        if "accuracy" in detail:
            bits.append(f"acc={detail['accuracy']:.0%} ({detail['hit']}/{detail['n']})")
        if "overall" in detail:
            bits.append(f"overall={detail.get('overall')}")
        if "doc_type_ok" in detail:
            bits.append(f"doc_ok={detail['doc_type_ok']}")
        print("  " + " ".join(bits), flush=True)
        for m in detail.get("miss") or []:
            print(f"    miss {m}", flush=True)

    summary = {
        "ok": all_ok,
        "n": len(rows),
        "by_kind": {},
        "rows": rows,
    }
    for r in rows:
        k = r.get("kind") or "?"
        summary["by_kind"].setdefault(k, {"n": 0, "pass": 0})
        summary["by_kind"][k]["n"] += 1
        if r.get("ok"):
            summary["by_kind"][k]["pass"] += 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
