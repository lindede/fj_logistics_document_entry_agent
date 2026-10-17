"""货代出口托运单（BKG 一类）：识别条件和字段规则放在一起。

版式特征：发货人 / 收货人 / 装货港标题落在矮矩形标题条里，值写在标题下方、
同一列宽之内。通知方只取标题条右沿以内的文字。
"""

from __future__ import annotations

import re
from typing import Any

from app.parse.html_struct import (
    Frame,
    Rule,
    Span,
    _column_spans,
    _containers,
    _enclosing_frame,
    _freight_value,
    _header_unit,
    _join,
    _qty_token,
    _vessel_voyage,
    split_number_unit,
)

FAMILY_ID = "forwarder_export_so"

# 别名已去掉空格和标点
_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("shipper", ("发货人", "shipper")),
    ("consignee", ("收货人", "consignee")),
    ("notify_party", ("通知方", "notifyparty")),
    ("vessel", ("船名", "vessel")),
    ("port_of_loading", ("装货港", "portofloading")),
    ("port_of_discharge", ("目的港", "portofdischarge")),
    ("container_type", ("箱型",)),
    ("container_qty", ("数量",)),
    ("marks", ("唛头及号码", "marksandnumbers")),
    ("packages", ("件数", "packages")),
    ("goods_desc", ("货品名称", "descriptionofgoods")),
    ("gross_weight", ("毛重",)),
    ("measurement", ("体积",)),
    ("freight", ("运费结算", "freightpaymentterms")),
)


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (text or "").lower())


def classify_span(span: Span) -> str | None:
    compact = _compact(span.text)
    if not compact:
        return None
    best: str | None = None
    best_len = 0
    for field, aliases in _LABELS:
        for alias in aliases:
            if alias in compact and len(alias) > best_len:
                best = field
                best_len = len(alias)
    return best


def matches(spans: list[Span], frames: list[Frame], rules: list[Rule]) -> bool:
    """发货人标题落在标题条矩形内，且同一份文字里有收货人和装货港。"""
    del rules
    shipper_in_frame = False
    has_consignee = False
    has_pol = False
    for span in spans:
        field = classify_span(span)
        if field == "shipper" and _enclosing_frame(span, frames) is not None:
            shipper_in_frame = True
        elif field == "consignee":
            has_consignee = True
        elif field == "port_of_loading":
            has_pol = True
    return shipper_in_frame and has_consignee and has_pol


def extract(spans: list[Span], frames: list[Frame], rules: list[Rule]) -> dict[str, Any]:
    labels = [(span, field) for span in spans if (field := classify_span(span))]
    label_ids = {id(span) for span, _field in labels}
    out: dict[str, Any] = {}
    for span, field in labels:
        if field in out:
            continue
        frame = _enclosing_frame(span, frames)
        if frame is None:
            if field == "freight":
                text = _freight_value(span, spans, labels, rules, classify_span)
                if text:
                    out["freight"] = text
            continue
        column, header_frames = _column_spans(span, frame, spans, frames, rules, label_ids)
        text = _join(column)
        if not text:
            continue
        header_unit = _header_unit(header_frames, spans)
        if field in {"packages", "gross_weight", "measurement"}:
            number, unit = split_number_unit(text, header_unit)
            if field == "packages":
                out["packages_qty"] = number
                if unit:
                    out["packages_unit"] = unit
            elif field == "gross_weight":
                out["gross_weight"] = number
                if unit:
                    out["weight_unit"] = unit
            else:
                out["measurement"] = number
                if unit:
                    out["measurement_unit"] = unit
        elif field == "container_type":
            out["_container_type"] = text
        elif field == "container_qty":
            out["_container_qty"] = _qty_token(text)
        elif field == "vessel":
            vessel, voyage = _vessel_voyage(text)
            if vessel:
                out["vessel"] = vessel
            out["voyage"] = voyage
        else:
            out[field] = text

    containers = _containers(out.pop("_container_type", None), out.pop("_container_qty", None))
    if containers:
        out["containers"] = containers
    return out
