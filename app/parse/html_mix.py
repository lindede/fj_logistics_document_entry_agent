"""html_mix：html_struct 与 html LLM 对照。主结果用 LLM，不一致记 MIX-DIFF WARN。"""

from __future__ import annotations

import json
from typing import Any

from app.config import BOOKING_FIELD_KEYS
from app.models import FieldIssue


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _containers_equal(left: Any, right: Any) -> bool:
    if not isinstance(left, list) or not isinstance(right, list):
        return left == right
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if not isinstance(a, dict) or not isinstance(b, dict):
            if a != b:
                return False
            continue
        if a.get("type") != b.get("type") or a.get("qty") != b.get("qty"):
            return False
    return True


def field_values_equal(key: str, struct_val: Any, llm_val: Any) -> bool:
    """规整后的字段是否一致。voyage 的 null 与 \"\" 算一样；两边都空算一样。"""
    if key == "voyage":
        return (struct_val or "") == (llm_val or "")
    if _is_empty(struct_val) and _is_empty(llm_val):
        return True
    if _is_empty(struct_val) or _is_empty(llm_val):
        return False
    if key == "containers":
        return _containers_equal(struct_val, llm_val)
    return struct_val == llm_val


def mix_diff_issues(
    struct_normalized: dict[str, Any],
    llm_normalized: dict[str, Any],
) -> list[FieldIssue]:
    """对比两侧规整结果，不一致字段 → MIX-DIFF WARN。"""
    issues: list[FieldIssue] = []
    for key in BOOKING_FIELD_KEYS:
        left = struct_normalized.get(key)
        right = llm_normalized.get(key)
        if field_values_equal(key, left, right):
            continue
        issues.append(
            FieldIssue(
                field=key,
                rule="MIX-DIFF",
                level="WARN",
                message=f"html_struct={_fmt(left)} / html={_fmt(right)}",
            )
        )
    return issues
