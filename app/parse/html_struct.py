"""PDF 文字坐标 + 矩形框 → 订舱字段。不调用大模型。

数字只在「整段是纯数字」或「纯数字 + 已知单位」时拆开。
拆不开的字符原样留下。单位来自数值本身，否则来自同一列表头上印的单位。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_LINE_Y_TOL = 3.0
_GAP_JOIN = 8.0

# 表头或数值后缀里出现这些才当成单位，不从代码里默认 KGS/CBM
_KNOWN_UNITS = frozenset(
    {
        "CTN",
        "CTNS",
        "KG",
        "KGS",
        "CBM",
        "M3",
        "PKG",
        "PKGS",
        "PLT",
        "PLTS",
        "BAG",
        "BAGS",
        "ROLL",
        "ROLLS",
        "TON",
        "TONS",
        "CARTON",
        "CARTONS",
    }
)

_EXACT_NUM = re.compile(r"^\d+(?:\.\d+)?$")
_NUM_UNIT = re.compile(r"^(\d+(?:\.\d+)?)([A-Za-z]+)$")


@dataclass
class Span:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Frame:
    x0: float
    y0: float
    x1: float
    y1: float
    page: int


@dataclass
class Rule:
    """横线或竖线。竖线时 x0==x1 为 x，y0/y1 为纵向范围。"""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    horizontal: bool


def split_number_unit(text: str, header_unit: str | None) -> tuple[Any, str | None]:
    """拆数量和单位。拆开后的两段拼回去必须和原文字逐字相同。

    ``25600KGS`` → (25600, "KGS")，因为 ``"25600" + "KGS"`` 就是原文。
    ``32.03`` → (32.03, header_unit)。header_unit 只来自文档表头。
    ``2560OKGS`` 拼不成「纯数字 + 已知单位」，毛重保持 ``2560OKGS``，O 留在字段里。
    """
    raw = (text or "").strip()
    if not raw:
        return raw, header_unit
    matched = _NUM_UNIT.fullmatch(raw)
    if matched:
        number_src, unit_src = matched.group(1), matched.group(2)
        # 数字原文和单位原文必须盖住每一个字符，不能先删掉再匹配
        if number_src + unit_src == raw and unit_src.upper() in _KNOWN_UNITS:
            return _as_number(number_src), unit_src.upper()
    if _EXACT_NUM.fullmatch(raw):
        return _as_number(raw), header_unit
    return raw, header_unit


def extract_html_struct(pdf_bytes: bytes) -> dict[str, Any]:
    """按已识别的运单版式抽取。未识别版式时抛错，不套用其它类的规则。"""
    from app.parse.struct_forms import classify_and_extract

    result = classify_and_extract(pdf_bytes)
    if result.family == "unknown":
        raise RuntimeError("html_struct 未识别运单版式，没有对应的提取规则")
    return result.fields


def _as_number(token: str) -> int | float:
    if "." in token:
        return float(token)
    return int(token)


def _qty_token(text: str) -> Any:
    raw = text.strip()
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    return raw


def _vessel_voyage(text: str) -> tuple[str, str]:
    body = re.sub(r"^BY\s+", "", text.strip(), flags=re.I)
    body = re.split(r"\s*ETD\b", body, maxsplit=1, flags=re.I)[0].strip(" :/-")
    matched = re.match(
        r"^(.+?)\s*(?:/|\bV\.)\s*([A-Za-z0-9][\w.-]*)$",
        body,
    )
    if matched:
        return matched.group(1).strip(), matched.group(2).strip()
    return body, ""


def _containers(ctype: Any, qty: Any) -> list[dict[str, Any]] | None:
    if ctype in (None, "") and qty in (None, ""):
        return None
    row: dict[str, Any] = {}
    if ctype not in (None, ""):
        row["type"] = ctype
    if qty not in (None, ""):
        row["qty"] = qty
    return [row] if row else None


def _unit_token(text: str) -> str | None:
    letters = re.sub(r"[^A-Za-z]", "", text).upper()
    if letters in _KNOWN_UNITS:
        return letters
    return None


def _read_layout(pdf_bytes: bytes) -> tuple[list[Span], list[Frame], list[Rule]]:
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    spans: list[Span] = []
    frames: list[Frame] = []
    rules: list[Rule] = []
    try:
        for i, page in enumerate(doc):
            page_no = i + 1
            spans.extend(_page_spans(page, page_no))
            for drawing in page.get_drawings():
                rect = drawing.get("rect")
                if rect is None:
                    continue
                width = rect.x1 - rect.x0
                height = rect.y1 - rect.y0
                if width > 120 and height < 2.5:
                    rules.append(
                        Rule(page_no, rect.x0, rect.y0, rect.x1, rect.y1, True)
                    )
                elif height > 20 and width < 2.5:
                    rules.append(
                        Rule(page_no, rect.x0, rect.y0, rect.x1, rect.y1, False)
                    )
                elif width > 8 and 8 < height < 40:
                    frames.append(Frame(rect.x0, rect.y0, rect.x1, rect.y1, page_no))
    finally:
        doc.close()
    return spans, frames, rules


def _page_spans(page: Any, page_no: int) -> list[Span]:
    words = sorted(page.get_text("words"), key=lambda w: (w[1], w[0]))
    lines: list[list] = []
    for word in words:
        if lines and abs(word[1] - lines[-1][0][1]) <= _LINE_Y_TOL:
            lines[-1].append(word)
        else:
            lines.append([word])
    spans: list[Span] = []
    for line in lines:
        line.sort(key=lambda w: w[0])
        bucket: list[tuple[float, float, float, float, list[str]]] = []
        for word in line:
            text = (word[4] or "").strip()
            if not text:
                continue
            if bucket and word[0] - bucket[-1][1] <= _GAP_JOIN:
                x0, _x1, y0, y1, parts = bucket[-1]
                bucket[-1] = (x0, max(_x1, word[2]), min(y0, word[1]), max(y1, word[3]), parts + [text])
            else:
                bucket.append((word[0], word[2], word[1], word[3], [text]))
        for x0, x1, y0, y1, parts in bucket:
            spans.append(Span(" ".join(parts), x0, y0, x1, y1, page_no))
    return spans


def _enclosing_frame(span: Span, frames: list[Frame]) -> Frame | None:
    found: list[Frame] = []
    for frame in frames:
        if frame.page != span.page:
            continue
        if frame.x0 - 1 <= span.cx <= frame.x1 + 1 and frame.y0 - 1 <= span.cy <= frame.y1 + 1:
            found.append(frame)
    if not found:
        return None
    return min(found, key=lambda f: (f.x1 - f.x0) * (f.y1 - f.y0))


def _x_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return min(a1, b1) - max(a0, b0)


def _same_column(frame: Frame, other: Frame) -> bool:
    overlap = _x_overlap(frame.x0, frame.x1, other.x0, other.x1)
    if overlap <= 0:
        return False
    narrow = min(frame.x1 - frame.x0, other.x1 - other.x0)
    return overlap >= narrow * 0.45


def _column_spans(
    label: Span,
    frame: Frame,
    spans: list[Span],
    frames: list[Frame],
    rules: list[Rule],
    label_ids: set[int],
) -> tuple[list[Span], list[Frame]]:
    y_start = frame.y1
    consumed = [frame]
    changed = True
    while changed:
        changed = False
        for other in frames:
            if other.page != frame.page or other in consumed:
                continue
            if other.y0 < y_start - 1.5 or other.y0 > y_start + 3:
                continue
            if not _same_column(frame, other):
                continue
            y_start = max(y_start, other.y1)
            consumed.append(other)
            changed = True

    page_bottom = max((s.y1 for s in spans if s.page == frame.page), default=y_start + 40)
    y_end = page_bottom
    for other in frames:
        if other.page != frame.page or other in consumed:
            continue
        if other.y0 < y_start - 0.5:
            continue
        if not _same_column(frame, other):
            continue
        y_end = min(y_end, other.y0)
    mid_x = (frame.x0 + frame.x1) / 2
    for rule in rules:
        if not rule.horizontal or rule.page != frame.page:
            continue
        if rule.y0 < y_start - 0.5:
            continue
        if rule.x0 - 2 <= mid_x <= rule.x1 + 2:
            y_end = min(y_end, rule.y0)

    picked = [
        span
        for span in spans
        if span.page == frame.page
        and id(span) not in label_ids
        and span.cy >= y_start - 0.5
        and span.cy <= y_end + 0.5
        and frame.x0 - 1 <= span.cx <= frame.x1 + 1
    ]
    picked.sort(key=lambda s: (s.y0, s.x0))
    return picked, consumed


def _header_unit(frames: list[Frame], spans: list[Span]) -> str | None:
    found: list[str] = []
    for span in spans:
        if not any(_span_in_frame(span, frame) for frame in frames):
            continue
        unit = _unit_token(span.text)
        if unit:
            found.append(unit)
    unique = list(dict.fromkeys(found))
    if len(unique) == 1:
        return unique[0]
    return None


def _span_in_frame(span: Span, frame: Frame) -> bool:
    return (
        frame.page == span.page
        and frame.x0 - 1 <= span.cx <= frame.x1 + 1
        and frame.y0 - 1 <= span.cy <= frame.y1 + 1
    )


def _freight_value(
    anchor: Span,
    spans: list[Span],
    labels: list[tuple[Span, str]],
    rules: list[Rule],
    classify_fn,
) -> str:
    horizontals = [
        rule
        for rule in rules
        if rule.horizontal
        and rule.page == anchor.page
        and rule.x0 - 2 <= anchor.cx <= rule.x1 + 2
    ]
    above = max((rule.y0 for rule in horizontals if rule.y0 <= anchor.y0 + 2), default=anchor.y0 - 16)
    below = min((rule.y0 for rule in horizontals if rule.y0 >= anchor.y1 - 1), default=anchor.y1 + 24)
    right_edge = min(
        (
            other.x0
            for other, field in labels
            if other.page == anchor.page
            and other.x0 > anchor.x1 + 8
            and above <= other.cy <= below
            and field != "freight"
        ),
        default=anchor.x1 + 280,
    )
    verticals = [
        rule.x0
        for rule in rules
        if not rule.horizontal
        and rule.page == anchor.page
        and rule.y0 - 2 <= anchor.cy <= rule.y1 + 2
        and rule.x0 > anchor.x1 - 1
    ]
    left_edge = min(verticals, default=anchor.x1)
    picked = [
        span
        for span in spans
        if span.page == anchor.page
        and id(span) != id(anchor)
        and classify_fn(span) is None
        and above <= span.cy <= below
        and left_edge - 1 <= span.cx <= right_edge - 1
    ]
    picked.sort(key=lambda s: (s.y0, s.x0))
    return _join(picked)


def _join(spans: list[Span]) -> str:
    if not spans:
        return ""
    lines: list[list[Span]] = [[spans[0]]]
    for span in spans[1:]:
        if abs(span.y0 - lines[-1][0].y0) <= _LINE_Y_TOL:
            lines[-1].append(span)
        else:
            lines.append([span])
    return "\n".join(" ".join(span.text for span in line) for line in lines)
