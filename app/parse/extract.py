from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any

from app.config import (
    GOLD_DIR,
    LLM_INPUT_MODE,
    LLM_MODEL,
    LLM_PDF_FALLBACK_VISION,
    LLM_TEXT_MODEL,
    OPENAI_TEMPERATURE,
    has_llm_key,
    make_openai_client,
    parse_backend,
)
from app.parse.pdf_io import assert_pdf, extract_text
from app.parse.pdf_pages import pdf_pages_as_png_data_urls, vision_user_content
from app.parse.schema_fill import fill_schema

logger = logging.getLogger("fj.parse")

BOOKING_HINTS = (
    "shipper",
    "consignee",
    "booking",
    "port of loading",
    "port of discharge",
    "vessel",
    "gross weight",
    "shipping order",
    "托运",
    "订舱",
    "装货港",
)


def _looks_like_booking(text: str) -> bool:
    lower = text.lower()
    hits = sum(1 for h in BOOKING_HINTS if h in lower)
    return hits >= 2 or "BKG SAMPLE" in text.upper()


def _text_layer_thin(text: str) -> bool:
    """扫描件/纯图 PDF 往往几乎抽不出文本；此时不能用文本门禁拒单。"""
    compact = re.sub(r"\s+", "", text or "")
    return len(compact) < 80


def fixture_extract() -> dict[str, Any]:
    """fixture 源数据：gold 文件原样（不做 normalize）。"""
    return json.loads((GOLD_DIR / "bkg_sample.json").read_text(encoding="utf-8"))


def _normalize_llm_fields(data: dict[str, Any]) -> dict[str, Any]:
    """轻量后处理：只做约定规整，不做版式规则抽取。"""
    out = fill_schema(data)
    if isinstance(out.get("marks"), str) and out["marks"].strip().upper() in {
        "N/M",
        "NM",
        "N.M",
        "",
    }:
        out["marks"] = None
    if out.get("voyage") is None:
        out["voyage"] = ""
    out["freight"] = _normalize_freight(out.get("freight"))
    voyage = out.get("voyage")
    if isinstance(voyage, str) and re.search(r"ETD", voyage, re.I):
        out["voyage"] = ""
    return out


def _extract_prompt_zh(*, as_pdf_file: bool = False) -> str:
    """与 prompt_lab v4_staged 对齐：先 ANALYSIS 再 JSON。"""
    src = (
        "下面直接给出完整出口货物托运单 PDF（可含多页）"
        if as_pdf_file
        else "下面是出口货物托运单 PDF 的页面图像（每页一张，可含多页）"
    )
    return (
        f"你是国际物流单证录入助手。{src}。\n"
        "\n"
        "请严格按两个阶段输出（同一次回复内完成），格式如下：\n"
        "\n"
        "### ANALYSIS\n"
        "（中文。按块简述单据上你看到的内容，并尽量带上关键栏的原文：\n"
        "货代/出具方、发货人、收货人、通知方、船名与航次、港口、箱型箱量、"
        "货名件数毛重体积、运费等。\n"
        "只写看得见的，不要猜。）\n"
        "\n"
        "### JSON\n"
        "（紧接着只输出一个 JSON 对象，不要 markdown 代码围栏，不要在 JSON 后再写其它文字。\n"
        "字段取值与上面 ANALYSIS 中对应栏位一致。\n"
        "字段必须且仅含：\n"
        "shipper, consignee, notify_party, vessel, voyage, port_of_loading, "
        "port_of_discharge, containers（[{type, qty}]）, packages_qty, packages_unit, "
        "goods_desc, gross_weight, weight_unit, measurement, measurement_unit, "
        "hs_code, marks, freight。\n"
        "\n"
        "规则：\n"
        "- 栏空或看不清 → null（voyage 无航次号用 \"\"）。\n"
        "- vessel：船名或船司简称；voyage：仅航次号（不要把开航日/ETD/电话当航次）。\n"
        "- marks：N/M、NM、无真实唛头 → null。\n"
        "- freight：P/C/E 或 null（预付/Prepaid→P；到付/Collect→C；约定/Elsewhere→E）。\n"
        "- packages_qty / containers[].qty：integer；gross_weight / measurement：number。\n"
        "\n"
        "JSON 形态示例（虚构占位，勿当作本题答案）：\n"
        '{"shipper":"...","consignee":"...","notify_party":"...","vessel":"...",'
        '"voyage":"","port_of_loading":"...","port_of_discharge":"...",'
        '"containers":[{"type":"...","qty":1}],"packages_qty":1,"packages_unit":"...",'
        '"goods_desc":"...","gross_weight":1.0,"weight_unit":"KGS","measurement":1.0,'
        '"measurement_unit":"CBM","hs_code":null,"marks":null,"freight":null}\n'
        "）"
    )


def _extract_prompt_html() -> str:
    """文字坐标 HTML + 文本模型。通知方只取标题正下方同一栏。"""
    return (
        "你是国际物流单证录入助手。下面给出的是出口货物托运单转成的 HTML（可含多页）。"
        "每个 div.line 是视觉上的一行，span 的 left 是横向位置。"
        "同一行里 left 差得远的 span 是不同栏，不要并成一栏。\n"
        "\n"
        "请严格按两个阶段输出（同一次回复内完成），格式如下：\n"
        "\n"
        "### ANALYSIS\n"
        "（中文。按块简述 HTML 里你看到的内容，并尽量带上关键栏的原文：\n"
        "货代/出具方、发货人、收货人、通知方、船名与航次、港口、箱型箱量、"
        "货名件数毛重体积、运费等。\n"
        "只写 HTML 里有的，不要猜。）\n"
        "\n"
        "### JSON\n"
        "（紧接着只输出一个 JSON 对象，不要 markdown 代码围栏，不要在 JSON 后再写其它文字。\n"
        "字段取值与上面 ANALYSIS 中对应栏位一致。\n"
        "字段必须且仅含：\n"
        "shipper, consignee, notify_party, vessel, voyage, port_of_loading, "
        "port_of_discharge, containers（[{type, qty}]）, packages_qty, packages_unit, "
        "goods_desc, gross_weight, weight_unit, measurement, measurement_unit, "
        "hs_code, marks, freight。\n"
        "\n"
        "规则：\n"
        "- 栏空或 HTML 里没有 → null（voyage 无航次号用 \"\"）。\n"
        "- 通知方 notify_party：只取「Notify Party / 通知方」标题正下方、"
        "且 left 与该标题同一栏的文字。"
        "标题右侧（left 明显更大）的货代抬头、地址、电话、邮箱不是通知方。\n"
        "- vessel：船名或船司简称；voyage：仅航次号（不要把开航日/ETD/电话当航次）。\n"
        "- marks：N/M、NM、无真实唛头 → null。\n"
        "- freight：P/C/E 或 null（预付/Prepaid→P；到付/Collect→C；约定/Elsewhere→E）。\n"
        "- packages_qty / containers[].qty：integer；gross_weight / measurement：number。\n"
        "\n"
        "JSON 形态示例（虚构占位，勿当作本题答案）：\n"
        '{"shipper":"...","consignee":"...","notify_party":"...","vessel":"...",'
        '"voyage":"","port_of_loading":"...","port_of_discharge":"...",'
        '"containers":[{"type":"...","qty":1}],"packages_qty":1,"packages_unit":"...",'
        '"goods_desc":"...","gross_weight":1.0,"weight_unit":"KGS","measurement":1.0,'
        '"measurement_unit":"CBM","hs_code":null,"marks":null,"freight":null}\n'
        "）"
    )


def _normalize_freight(value: Any) -> str | None:
    """把单据常见写法规整为 P/C/E；无法识别则 null。"""
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    f = raw.upper()
    if f in {"P", "C", "E"}:
        return f
    if "PREPAID" in f or "预付" in raw:
        return "P"
    if "COLLECT" in f or "到付" in raw:
        return "C"
    if (
        f in {"E", "ELSEWHERE"}
        or "PAYABLE ELSEWHERE" in f
        or "约定" in raw
        or "第三地" in raw
    ):
        return "E"
    return None


def _parse_json_object(blob: str) -> dict[str, Any] | None:
    raw = (blob or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        matches = list(re.finditer(r"\{[\s\S]*\}", raw))
        for m in reversed(matches):
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    return None


def _extract_llm_analysis(content: str) -> str | None:
    """从 staged 回复中取出 ### ANALYSIS 正文（若无则为 None）。"""
    text = content or ""
    m = re.search(
        r"###\s*ANALYSIS\s*\n([\s\S]*?)(?=###\s*JSON|\Z)",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    body = m.group(1).strip()
    return body or None


def _parse_llm_json_content(content: str) -> dict[str, Any]:
    """支持纯 JSON，或 v4 分阶段「### ANALYSIS … ### JSON …」。只解析 JSON，不 normalize。"""
    text = content or ""
    m_j = re.search(r"###\s*JSON\s*\n([\s\S]*)", text, flags=re.IGNORECASE)
    blob = m_j.group(1).strip() if m_j else text.strip()
    data = _parse_json_object(blob)
    if data is None and m_j:
        data = _parse_json_object(text)
    if data is None:
        raise RuntimeError(f"LLM returned non-JSON: {text[:300]}")
    return data


def _parse_llm_response(content: str) -> tuple[str | None, dict[str, Any]]:
    """解析模型回复 → (llm_analysis, raw_json_dict)。raw 未经 normalize。"""
    return _extract_llm_analysis(content), _parse_llm_json_content(content)


def _call_chat(
    client: Any,
    messages: list[dict[str, Any]],
    *,
    use_json_format: bool,
    model: str | None = None,
) -> str:
    chosen = model or LLM_MODEL
    kwargs: dict[str, Any] = {
        "model": chosen,
        "messages": messages,
        "temperature": OPENAI_TEMPERATURE,
    }
    extra: dict[str, Any] = {"thinking": {"type": "disabled"}}
    try:
        if use_json_format:
            resp = client.chat.completions.create(
                **kwargs, response_format={"type": "json_object"}, extra_body=extra
            )
        else:
            resp = client.chat.completions.create(**kwargs, extra_body=extra)
    except Exception:
        resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""
    if not content.strip():
        raise RuntimeError(
            f"模型返回空 content（model={chosen}）。"
        )
    return content


def llm_extract_from_pdf(pdf_bytes: bytes, text_fallback: str = "") -> dict[str, Any]:
    """主路径：file_url 直传 PDF；可选回退页图 / 文本。

    返回 {"raw_extracted_data": dict, "llm_analysis": str|None}。
    raw 为模型 JSON 原样，不做 normalize。
    """
    mode = (os.getenv("LLM_INPUT_MODE") or LLM_INPUT_MODE or "pdf").strip().lower()
    if mode in {"html_struct", "xtml_struct"}:
        from app.parse.html_struct import extract_html_struct

        logger.info("LLM_INPUT_MODE=%s（不调用大模型）", mode)
        return {"raw_extracted_data": extract_html_struct(pdf_bytes), "llm_analysis": None}

    if not has_llm_key():
        raise RuntimeError(
            "PARSE_BACKEND=llm 但未配置 OPENAI_API_KEY（请参考 kb_pdf_to_vdb 的 .env）"
        )
    client = make_openai_client()

    def _pack(content: str, **extra: Any) -> dict[str, Any]:
        analysis, raw = _parse_llm_response(content)
        out: dict[str, Any] = {"raw_extracted_data": raw, "llm_analysis": analysis}
        out.update(extra)
        return out

    def run_pdf_file() -> dict[str, Any]:
        prompt = _extract_prompt_zh(as_pdf_file=True)
        data_url = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode(
            "ascii"
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "file_url", "file_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        return _pack(_call_chat(client, messages, use_json_format=False))

    def run_vision() -> dict[str, Any]:
        prompt = _extract_prompt_zh(as_pdf_file=False)
        urls, vision_paths = pdf_pages_as_png_data_urls(pdf_bytes)
        if not urls:
            raise RuntimeError("PDF 无法渲染为页面图像")
        messages = [{"role": "user", "content": vision_user_content(urls, prompt)}]
        return _pack(
            _call_chat(client, messages, use_json_format=False),
            vision_page_paths=vision_paths,
        )

    def run_text() -> dict[str, Any]:
        prompt = _extract_prompt_zh(as_pdf_file=False)
        messages = [
            {
                "role": "system",
                "content": "你是国际物流单证录入助手，从托运单文本抽取 JSON 字段。",
            },
            {
                "role": "user",
                "content": f"{prompt}\n\n（注意：以下为文本层，版面可能已丢失）\n{text_fallback[:12000]}",
            },
        ]
        logger.warning("LLM_INPUT_MODE=text：版面会丢失，建议 pdf 或 vision")
        return _pack(_call_chat(client, messages, use_json_format=True))

    def run_html() -> dict[str, Any]:
        from app.parse.html_layout import words_to_html

        doc_html = words_to_html(pdf_bytes)
        if "<span" not in doc_html:
            raise RuntimeError(
                "LLM_INPUT_MODE=html 需要 PDF 文字层，当前抽不出带坐标的文字"
            )
        prompt = _extract_prompt_html()
        messages = [
            {"role": "user", "content": f"{prompt}\n\n--- HTML ---\n{doc_html}"}
        ]
        logger.info(
            "LLM_INPUT_MODE=html model=%s html_chars=%s",
            LLM_TEXT_MODEL,
            len(doc_html),
        )
        return _pack(
            _call_chat(
                client,
                messages,
                use_json_format=False,
                model=LLM_TEXT_MODEL,
            )
        )

    def run_html_mix() -> dict[str, Any]:
        from app.models import FieldIssue
        from app.parse.html_mix import mix_diff_issues
        from app.parse.struct_forms import UNKNOWN_FAMILY, classify_and_extract

        classified = classify_and_extract(pdf_bytes)
        try:
            llm_packed = run_html()
        except Exception as exc:
            raise RuntimeError(f"html_mix：html LLM 失败：{exc}") from exc
        llm_raw = llm_packed["raw_extracted_data"]
        if classified.family == UNKNOWN_FAMILY:
            diffs = [
                FieldIssue(
                    field="_document",
                    rule="MIX-FORM",
                    level="WARN",
                    message="未识别版式，结构侧未抽取",
                )
            ]
        else:
            struct_norm = _normalize_llm_fields(classified.fields)
            llm_norm = _normalize_llm_fields(llm_raw)
            diffs = mix_diff_issues(struct_norm, llm_norm)
        logger.info(
            "LLM_INPUT_MODE=html_mix form_family=%s mix_diff_fields=%s",
            classified.family,
            [i.field for i in diffs],
        )
        out = dict(llm_packed)
        out["form_family"] = classified.family
        out["html_struct_raw"] = classified.fields
        out["mix_diff_issues"] = [i.model_dump() for i in diffs]
        return out

    if mode == "html_mix":
        return run_html_mix()
    if mode == "html":
        return run_html()
    if mode == "text":
        return run_text()
    if mode == "vision":
        return run_vision()

    try:
        return run_pdf_file()
    except Exception as exc:
        if not LLM_PDF_FALLBACK_VISION:
            raise
        logger.warning("PDF file_url 失败，回退页图 vision：%s", exc)
        return run_vision()


def estimate_confidence(raw: dict[str, Any], backend: str) -> dict[str, float]:
    conf: dict[str, float] = {}
    base = 0.85 if backend == "fixture" else 0.75
    for k, v in raw.items():
        if v is None or v == "" or v == []:
            conf[k] = 0.0 if k != "voyage" else 0.7
        else:
            conf[k] = base
    for k in ("hs_code", "marks", "freight"):
        if raw.get(k) is None:
            conf[k] = 0.8
    return conf


def parse_pdf_bytes(data: bytes) -> dict[str, Any]:
    assert_pdf(data)
    text = extract_text(data)
    backend = parse_backend()

    thin = _text_layer_thin(text)
    if thin:
        doc_type_ok = True
        if backend == "llm":
            logger.info(
                "text layer thin/empty; skip pypdf booking gate, defer to multimodal"
            )
    else:
        doc_type_ok = _looks_like_booking(text)

    if not doc_type_ok:
        raw: dict[str, Any] = {}
        normalized = _normalize_llm_fields({})
        return {
            "raw_extracted_data": raw,
            "normalized_data": normalized,
            "llm_analysis": None,
            "doc_type_ok": False,
            "text": text,
            "backend": backend,
            "field_confidence": estimate_confidence(normalized, backend),
            "error": "document does not look like a booking/shipping order",
        }

    llm_analysis: str | None = None
    vision_page_paths: list[str] = []
    html_struct_raw = None
    mix_diff_issues: list[Any] = []
    form_family = None
    if backend == "fixture":
        raw = fixture_extract()
        mode = "fixture"
    elif backend == "llm":
        mode = (os.getenv("LLM_INPUT_MODE") or LLM_INPUT_MODE or "pdf").strip().lower()
        if thin and mode == "text":
            logger.warning("scanned PDF + LLM_INPUT_MODE=text will fail; forcing pdf")
            os.environ["LLM_INPUT_MODE"] = "pdf"
            mode = "pdf"
        packed = llm_extract_from_pdf(data, text_fallback=text)
        raw = packed["raw_extracted_data"]
        llm_analysis = packed.get("llm_analysis")
        vision_page_paths = list(packed.get("vision_page_paths") or [])
        html_struct_raw = packed.get("html_struct_raw")
        mix_diff_issues = list(packed.get("mix_diff_issues") or [])
        form_family = packed.get("form_family")
    else:
        raise ValueError(
            f"unknown PARSE_BACKEND={backend!r}; expected 'llm' or 'fixture'"
        )

    normalized = _normalize_llm_fields(raw)
    result: dict[str, Any] = {
        "raw_extracted_data": raw,
        "normalized_data": normalized,
        "llm_analysis": llm_analysis,
        "doc_type_ok": True,
        "text": text,
        "backend": f"{backend}:{mode}" if backend == "llm" else backend,
        "field_confidence": estimate_confidence(
            normalized, "llm" if backend == "llm" else backend
        ),
        "text_layer_thin": thin,
        "vision_page_paths": vision_page_paths,
    }
    if backend == "llm":
        if form_family:
            result["form_family"] = form_family
        if html_struct_raw is not None:
            result["html_struct_raw"] = html_struct_raw
        if mix_diff_issues:
            result["mix_diff_issues"] = mix_diff_issues
    return result
