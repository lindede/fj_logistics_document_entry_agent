from __future__ import annotations

import re
from typing import Any


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
        if status != "Idle":
            return "replace_conflict"
        return "open_booking"
    if not t:
        return "noop"

    if any(k in t for k in ("提交", "确认提交", "submit", "confirm")):
        return "submit"
    if any(k in t for k in ("作废", "取消", "void", "discard", "放弃")):
        return "void"
    if any(k in t for k in ("换票", "新单", "重新开票", "replace")):
        return "replace_confirm"
    if "开票" in t or "parse" in t or "录入" in t:
        return "open_need_pdf" if not has_pdf else "open_booking"

    # 自然语言改字段
    if _nl_patch(t):
        return "nl_patch"
    if status == "Idle" and _nl_patch(t):
        return "idle_patch_ask"
    return "unknown"


def _nl_patch(t: str) -> dict[str, Any] | None:
    """解析简单动态指令，如 KGS→TON / 毛重单位换成 TON。"""
    # 重量单位
    m = re.search(
        r"(毛重)?\s*单位.*(从\s*)?(kgs|kg|ton|mt)\s*(换成|改为|改成|到|->|→)\s*(kgs|kg|ton|mt)",
        t,
        re.I,
    )
    if m:
        to_u = m.group(5).upper()
        if to_u == "KG":
            to_u = "KGS"
        return {"weight_unit": to_u, "_convert_weight": True}

    m = re.search(r"(kgs|kg)\s*(->|→|换成|改为)\s*(ton|mt)", t, re.I)
    if m:
        return {"weight_unit": m.group(3).upper().replace("MT", "TON"), "_convert_weight": True}

    m = re.search(r"(ton|mt)\s*(->|→|换成|改为)\s*(kgs|kg)", t, re.I)
    if m:
        return {"weight_unit": "KGS", "_convert_weight": True}

    m = re.search(r"船名.*(改为|改成|换成)\s*([a-z0-9 \-]+)", t, re.I)
    if m:
        return {"vessel": m.group(2).strip().upper()}

    m = re.search(r"(装货港|pol).*(改为|改成|换成)\s*(.+)$", t, re.I)
    if m:
        return {"port_of_loading": m.group(3).strip()}

    m = re.search(r"(目的港|卸货港|pod).*(改为|改成|换成)\s*(.+)$", t, re.I)
    if m:
        return {"port_of_discharge": m.group(3).strip()}

    return None


def parse_nl_patches(text: str) -> dict[str, Any] | None:
    return _nl_patch((text or "").strip().lower())


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
