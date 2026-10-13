from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any

from app.config import (
    GOLD_DIR,
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_INPUT_MODE,
    LLM_MODEL,
    LLM_PDF_FALLBACK_VISION,
    OPENAI_TEMPERATURE,
    has_llm_key,
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
    gold = json.loads((GOLD_DIR / "bkg_sample.json").read_text(encoding="utf-8"))
    return fill_schema(gold)


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
    freight = out.get("freight")
    if isinstance(freight, str) and freight.strip():
        f = freight.strip().upper()
        if f in {"P", "C", "E"}:
            out["freight"] = f
        elif "PREPAID" in f or "预付" in freight:
            out["freight"] = "P"
        elif "COLLECT" in f or "到付" in freight:
            out["freight"] = "C"
        else:
            out["freight"] = None
    voyage = out.get("voyage")
    if isinstance(voyage, str) and re.search(r"ETD", voyage, re.I):
        out["voyage"] = ""
    return out


def _extract_prompt_zh(*, as_pdf_file: bool = False) -> str:
    src = (
        "下面直接给出完整出口货物托运单 PDF 文件（可含多页，请按页阅读版面）"
        if as_pdf_file
        else "下面是出口货物托运单 PDF 的页面图像（每页一张，保留版面位置）"
    )
    return (
        f"你是国际物流单证录入助手。{src}，请抽取业务字段。\n"
        "只返回一个 JSON 对象，不要 markdown，不要解释。\n"
        "\n"
        "【反幻觉 / 最高优先级】\n"
        "- 只依据单据上可见文字与版面；禁止猜测、补全、推理「应该是多少」。\n"
        "- 看不清、被裁切、跨页对不上、或栏位空白 → 该字段必须 null"
        "（voyage 例外：无航次号时用 \"\"，不要用 ETD/日期冒充）。\n"
        "- 禁止为了「字段齐全」或「类型好看」而编造公司名、港口、数字、箱型。\n"
        "- 禁止用训练记忆或常见样例值填充；本单没有的内容一律 null。\n"
        "- 不确定就 null，把问题留给后续校验与人工，不要假装抽到了。\n"
        "\n"
        "字段 key 必须为（且仅这些）：\n"
        "shipper, consignee, notify_party, vessel, voyage, port_of_loading, "
        "port_of_discharge, containers（[{type, qty}] 数组）, packages_qty, packages_unit, "
        "goods_desc, gross_weight, weight_unit, measurement, measurement_unit, "
        "hs_code, marks, freight。\n"
        "\n"
        "类型约定（有证据时才填该类型；无证据用 null，勿用空字符串凑数）：\n"
        "- 文本：非空 string；packages_qty / containers[].qty：integer；"
        "gross_weight / measurement：number。\n"
        "- marks：N/M 或无真实唛头 → null。\n"
        "- vessel：只要船名/船司简称，不要电话或地址。\n"
        "- consignee 与 notify_party 分栏读取，禁止合并或互换。\n"
        "- freight 仅可为 P / C / E 或 null（单据写预付可映射为 P）。\n"
        "\n"
        "格式示例（虚构占位，勿当作本题答案）：\n"
        '{"shipper":"...","packages_qty":1,"gross_weight":1.0,"marks":null,"freight":null}'
    )


def _parse_llm_json_content(content: str) -> dict[str, Any]:
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned non-JSON: {content[:300]}") from exc


def _call_chat(client: Any, messages: list[dict[str, Any]], *, use_json_format: bool) -> str:
    kwargs: dict[str, Any] = {
        "model": LLM_MODEL,
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
            f"多模态模型返回空 content（model={LLM_MODEL}）。"
            "请确认使用视觉/文件模型，如 glm-4.6v-flash。"
        )
    return content


def llm_extract_from_pdf(pdf_bytes: bytes, text_fallback: str = "") -> dict[str, Any]:
    """主路径：file_url 直传 PDF；可选回退页图 / 文本。"""
    if not has_llm_key():
        raise RuntimeError(
            "PARSE_BACKEND=llm 但未配置 OPENAI_API_KEY（请参考 kb_pdf_to_vdb 的 .env）"
        )
    from openai import OpenAI

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    mode = (os.getenv("LLM_INPUT_MODE") or LLM_INPUT_MODE or "pdf").strip().lower()

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
        content = _call_chat(client, messages, use_json_format=False)
        return _normalize_llm_fields(_parse_llm_json_content(content))

    def run_vision() -> dict[str, Any]:
        prompt = _extract_prompt_zh(as_pdf_file=False)
        urls = pdf_pages_as_png_data_urls(pdf_bytes)
        if not urls:
            raise RuntimeError("PDF 无法渲染为页面图像")
        messages = [{"role": "user", "content": vision_user_content(urls, prompt)}]
        content = _call_chat(client, messages, use_json_format=False)
        return _normalize_llm_fields(_parse_llm_json_content(content))

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
        content = _call_chat(client, messages, use_json_format=True)
        return _normalize_llm_fields(_parse_llm_json_content(content))

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
        raw = fill_schema({})
        return {
            "raw_extracted_data": raw,
            "doc_type_ok": False,
            "text": text,
            "backend": backend,
            "field_confidence": estimate_confidence(raw, backend),
            "error": "document does not look like a booking/shipping order",
        }

    if backend == "fixture":
        raw = fixture_extract()
        mode = "fixture"
    elif backend == "llm":
        mode = (os.getenv("LLM_INPUT_MODE") or LLM_INPUT_MODE or "pdf").strip().lower()
        if thin and mode == "text":
            logger.warning("scanned PDF + LLM_INPUT_MODE=text will fail; forcing pdf")
            os.environ["LLM_INPUT_MODE"] = "pdf"
            mode = "pdf"
        raw = llm_extract_from_pdf(data, text_fallback=text)
    else:
        raise ValueError(
            f"unknown PARSE_BACKEND={backend!r}; expected 'llm' or 'fixture'"
        )

    return {
        "raw_extracted_data": raw,
        "doc_type_ok": True,
        "text": text,
        "backend": f"{backend}:{mode}" if backend == "llm" else backend,
        "field_confidence": estimate_confidence(
            raw, "llm" if backend == "llm" else backend
        ),
        "text_layer_thin": thin,
    }
