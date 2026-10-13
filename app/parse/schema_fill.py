from __future__ import annotations

import re
from typing import Any

from app.config import BOOKING_FIELD_KEYS, OPTIONAL_NULL_KEYS
from app.parse.normalize import normalize_extracted_text

# 仅当整段是「数字字面量」才转；含字母/多小数点等一律原样返回
_INT_RE = re.compile(r"^[+-]?\d+$")
_INT_DOT_ZERO_RE = re.compile(r"^[+-]?\d+\.0+$")
_NUM_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")


def _as_int(value: Any) -> Any:
    """安全转 integer：已是 int 保留；纯数字字符串才转；否则原样。"""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # 仅 160.0 这类整值 float → int；160.5 不强行截断
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if not s:
            return value
        if _INT_RE.fullmatch(s):
            return int(s)
        if _INT_DOT_ZERO_RE.fullmatch(s):
            return int(float(s))
        return value
    return value


def _as_number(value: Any) -> Any:
    """安全转 number：已是 int/float 保留；纯数字字符串才转；否则原样。"""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) if isinstance(value, float) else value
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if not s or not _NUM_RE.fullmatch(s):
            return value
        try:
            num = float(s)
        except ValueError:
            return value
        # 整数形态的 number 字段保持 float 也可；schema 用 number 接受 int
        if num.is_integer() and "." not in s and "e" not in s.lower():
            return int(num)
        return num
    return value


def _coerce_containers(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    out: list[Any] = []
    for item in value:
        if not isinstance(item, dict):
            out.append(item)
            continue
        row = dict(item)
        if "qty" in row:
            row["qty"] = _as_int(row["qty"])
        out.append(row)
    return out


def _coerce_types(data: dict[str, Any]) -> dict[str, Any]:
    """在已有值上做安全类型规整，绝不把非数字强转成数字。"""
    data["packages_qty"] = _as_int(data.get("packages_qty"))
    data["gross_weight"] = _as_number(data.get("gross_weight"))
    data["measurement"] = _as_number(data.get("measurement"))
    if "containers" in data:
        data["containers"] = _coerce_containers(data.get("containers"))
    return data


def fill_schema(data: dict[str, Any] | None) -> dict[str, Any]:
    """按 FLD 补齐全部 key，并对明显的数字字符串做安全类型规整。

    扩展字段缺省为 null，voyage 缺省为空串。
    流水线：字符标准化（VAL-03）→ 补 key → 安全数字规整。
    类型规整：仅当值已是合法数字字面量才转 int/number；否则原样留给 validate。
    """
    src = normalize_extracted_text(data or {})
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
    return _coerce_types(out)
