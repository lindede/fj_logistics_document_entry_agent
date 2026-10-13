"""VAL-03：抽取结果的输入标准化（字符清洗 / 统一），不编造业务内容。"""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any

from app.config import BOOKING_FIELD_KEYS

# 奇异空白 → 普通空格；多空白折叠
_WS_RE = re.compile(r"[\t\r\n\f\v]+")
_MULTI_SPACE_RE = re.compile(r" {2,}")

_DASHES = (
    "\u2010",  # hyphen
    "\u2011",
    "\u2012",
    "\u2013",  # en dash
    "\u2014",  # em dash
    "\u2212",  # minus
    "\uff0d",  # fullwidth hyphen-minus（NFKC 后通常已是 -，兜底）
)
_QUOTES = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u00b4": "'",
    "\u0060": "'",
}


def normalize_text(value: str) -> str:
    """单段文本：NFKC → 空白/破折号/引号统一 → strip。不改语义、不补内容。"""
    if not isinstance(value, str):
        return value
    s = unicodedata.normalize("NFKC", value)
    s = s.replace("\u00a0", " ").replace("\u3000", " ")
    s = _WS_RE.sub(" ", s)
    for d in _DASHES:
        s = s.replace(d, "-")
    for src, dst in _QUOTES.items():
        s = s.replace(src, dst)
    s = _MULTI_SPACE_RE.sub(" ", s)
    return s.strip()


def normalize_extracted_text(data: dict[str, Any] | None) -> dict[str, Any]:
    """对抽取 dict 中的字符串字段做字符级标准化（VAL-03）。

    - 只处理已知 FLD key 及 containers[].type
    - 数字字段若仍是 str，也会做字符清洗，便于后续安全转类型
    - 不把空串改成业务默认值，不编造
    """
    src = deepcopy(data or {})
    out: dict[str, Any] = {}
    for key, val in src.items():
        if key == "containers" and isinstance(val, list):
            rows: list[Any] = []
            for item in val:
                if not isinstance(item, dict):
                    rows.append(item)
                    continue
                row = dict(item)
                if isinstance(row.get("type"), str):
                    row["type"] = normalize_text(row["type"])
                if isinstance(row.get("qty"), str):
                    row["qty"] = normalize_text(row["qty"])
                rows.append(row)
            out[key] = rows
        elif key in BOOKING_FIELD_KEYS and isinstance(val, str):
            out[key] = normalize_text(val)
        else:
            out[key] = val
    return out
