from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.config import CONFIDENCE_THRESHOLD
from app.models import FieldIssue, ValidationReport
from app.validate import rules


def _overall(issues: list[FieldIssue], low_conf: list[str]) -> str:
    levels = {i.level for i in issues}
    if "FAIL" in levels:
        return "FAIL"
    if "WARN" in levels or low_conf:
        return "WARN"
    return "PASS"


def _suggested(overall: str) -> str:
    if overall == "FAIL":
        return "await_human_fix_or_void"
    if overall == "WARN":
        return "await_confirm_review_warnings"
    return "await_confirm_or_auto_submit"


def validate_booking(
    raw: dict[str, Any],
    field_confidence: dict[str, float] | None = None,
) -> tuple[dict[str, Any], ValidationReport]:
    """只校验、不补齐字段。FLD key 补全应在解析侧 `fill_schema` 完成。"""
    data = deepcopy(raw or {})

    issues: list[FieldIssue] = []
    from app.validate.schema_check import check_schema

    issues.extend(check_schema(data))
    issues.extend(rules.check_structure(data))
    issues.extend(rules.br_01_ports_differ(data))
    issues.extend(rules.br_02_ranges(data))
    issues.extend(rules.br_03_vessel(data))
    issues.extend(rules.br_04_shipper_consignee(data))
    issues.extend(rules.br_05_no_fabricate(data))
    issues.extend(rules.br_06_ports_whitelist(data))

    conf = field_confidence or {}
    low = [
        k
        for k, v in conf.items()
        if k
        not in ("hs_code", "marks", "freight", "voyage")
        and v < CONFIDENCE_THRESHOLD
        and data.get(k) is not None
        and data.get(k) != ""
    ]
    # 必填缺失也算低置信触发人工
    for issue in issues:
        if issue.rule == "STRUCT-REQUIRED" and issue.field not in low:
            low.append(issue.field)

    overall = _overall(issues, low)
    report = ValidationReport(
        overall=overall,
        issues=issues,
        field_confidence=conf,
        suggested_action=_suggested(overall),
        low_confidence_fields=low,
    )
    # 原样返回输入副本（不做 schema 补全）
    return data, report
