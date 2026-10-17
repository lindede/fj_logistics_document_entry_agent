"""按运单提供者版式选择结构抽取。未识别时不套用任何一类的规则。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.parse.html_struct import _read_layout
from app.parse.struct_forms import forwarder_export_so

UNKNOWN_FAMILY = "unknown"

_FAMILIES = (forwarder_export_so,)


@dataclass
class StructResult:
    family: str
    fields: dict[str, Any]


def classify_and_extract(pdf_bytes: bytes) -> StructResult:
    spans, frames, rules = _read_layout(pdf_bytes)
    if not spans:
        raise RuntimeError("html_struct 需要 PDF 文字层，当前抽不出带坐标的文字")
    for family in _FAMILIES:
        if family.matches(spans, frames, rules):
            return StructResult(family.FAMILY_ID, family.extract(spans, frames, rules))
    return StructResult(UNKNOWN_FAMILY, {})
