from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.config import BOOKING_FIELD_KEYS, OPTIONAL_NULL_KEYS


def fill_schema(data: dict[str, Any] | None) -> dict[str, Any]:
    """按 FLD 补齐全部 key；扩展字段缺省为 null，voyage 缺省为空串。"""
    src = deepcopy(data or {})
    # 兼容原文表头 Cargo
    if "goods_desc" not in src and "Cargo" in src:
        src["goods_desc"] = src.pop("Cargo")
    out: dict[str, Any] = {}
    for key in BOOKING_FIELD_KEYS:
        if key in src and src[key] is not None and src[key] != "":
            out[key] = src[key]
        elif key == "voyage":
            out[key] = src.get("voyage") if src.get("voyage") is not None else ""
        elif key in OPTIONAL_NULL_KEYS:
            val = src.get(key)
            out[key] = None if val in ("", None) else val
        else:
            out[key] = src.get(key, None)
    return out
