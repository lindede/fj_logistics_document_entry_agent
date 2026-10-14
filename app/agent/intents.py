from __future__ import annotations

from typing import Any

from app.agent.nl_patch import parse_nl_patches


def detect_intent(
    text: str | None,
    *,
    has_pdf: bool,
    patches: dict[str, Any] | None,
    status: str,
) -> str:
    t = (text or "").strip().lower()
    if patches:
        return "patch_fields"
    if has_pdf:
        if status not in {"Idle", "Done"}:
            return "replace_conflict"
        return "open_booking"
    if not t:
        return "noop"

    # Done：文字一律走存盘修正，避免「确认/取消」等词误进 submit/void
    if status == "Done":
        return "nl_patch"

    if any(k in t for k in ("提交", "确认提交", "submit", "confirm")):
        return "submit"
    if any(k in t for k in ("作废", "取消", "void", "discard", "放弃")):
        return "void"
    if any(k in t for k in ("换票", "新单", "重新开票", "replace")):
        return "replace_confirm"
    if "开票" in t or "parse" in t or "录入" in t:
        return "open_need_pdf" if not has_pdf else "open_booking"

    # 其余自然语言交给 LLM/回退解析（session 里调 parse_nl_patches）
    return "nl_patch"


def apply_weight_unit_conversion(data: dict[str, Any], new_unit: str) -> dict[str, Any]:
    out = dict(data)
    old = str(out.get("weight_unit") or "").upper()
    new_u = new_unit.upper()
    if new_u == "MT":
        new_u = "TON"
    if old == "KG":
        old = "KGS"
    gw = out.get("gross_weight")
    if gw is not None and old and new_u and old != new_u:
        try:
            val = float(gw)
            if old == "KGS" and new_u == "TON":
                val = val / 1000.0
            elif old == "TON" and new_u == "KGS":
                val = val * 1000.0
            out["gross_weight"] = round(val, 6) if new_u == "TON" else round(val, 3)
        except (TypeError, ValueError):
            pass
    out["weight_unit"] = new_u
    return out


# 兼容旧 import
__all__ = ["detect_intent", "parse_nl_patches", "apply_weight_unit_conversion"]
