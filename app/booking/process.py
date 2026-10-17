from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import DEBUG_DIR, PARSE_DEBUG_DUMP
from app.models import BookingRecord, FieldIssue, ValidationReport
from app.observe import metrics_stub
from app.parse.extract import parse_pdf_bytes
from app.parse.pdf_io import resolve_pdf_input
from app.validate import validate_booking

logger = logging.getLogger("fj.booking")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump_parse_debug(
    *,
    record: BookingRecord,
    parsed: dict[str, Any],
    filename: str,
) -> None:
    """PARSE_DEBUG_DUMP 开启时写入 data/debug/parse_*.json。"""
    if not PARSE_DEBUG_DUMP:
        return
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sid = (record.session_id or "nosession")[:8]
    path = DEBUG_DIR / f"parse_{ts}_{sid}.json"
    report = record.validation_report
    payload = {
        "dumped_at": _now(),
        "session_id": record.session_id,
        "filename": filename,
        "backend": parsed.get("backend"),
        "doc_type_ok": parsed.get("doc_type_ok"),
        "text_layer_thin": parsed.get("text_layer_thin"),
        "pdf_text": parsed.get("text"),
        "vision_page_paths": parsed.get("vision_page_paths") or [],
        "llm_analysis": record.llm_analysis,
        "raw_extracted_data": record.raw_extracted_data,
        "normalized_data": record.normalized_data,
        "validated_data": record.validated_data,
        "validation_report": report.model_dump() if report else None,
        "field_confidence": parsed.get("field_confidence"),
        "html_struct_raw": parsed.get("html_struct_raw"),
        "mix_diff_issues": parsed.get("mix_diff_issues"),
        "status": record.status,
        "message": record.message,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("PARSE_DEBUG_DUMP → %s", path)


def _status_for(report: ValidationReport, doc_type_ok: bool) -> tuple[str, str]:
    if not doc_type_ok:
        return "AwaitHuman", "单据类型不是托运/订舱单"
    if report.overall == "FAIL" or report.low_confidence_fields:
        return "AwaitHuman", "校验未通过或低置信，请修正后重验或作废"
    if report.overall == "WARN":
        return "AwaitConfirm", "存在警告，请确认后提交或修改"
    return "AwaitConfirm", "校验通过，请确认提交"


def process_booking(
    file_path: str | None = None,
    base64_pdf: str | None = None,
    *,
    session_id: str | None = None,
) -> BookingRecord:
    """解析 + 校验 → BookingRecord（业务核心产物）。"""
    pdf_bytes, filename = resolve_pdf_input(file_path, base64_pdf)
    parsed = parse_pdf_bytes(pdf_bytes)
    raw = parsed["raw_extracted_data"]
    normalized = parsed.get("normalized_data") or raw
    llm_analysis = parsed.get("llm_analysis")
    conf = parsed["field_confidence"]
    doc_ok = bool(parsed.get("doc_type_ok", True))

    # 校验落在 normalize 之后，不污染 raw
    validated, report = validate_booking(normalized, conf)
    mix_raw = list(parsed.get("mix_diff_issues") or [])
    for item in mix_raw:
        report.issues.append(FieldIssue(**item))
    if mix_raw and report.overall == "PASS":
        report.overall = "WARN"
        report.suggested_action = "await_confirm_review_warnings"
    if not doc_ok:
        report.overall = "FAIL"
        report.issues.insert(
            0,
            FieldIssue(
                field="_document",
                rule="DOC-TYPE",
                level="FAIL",
                message=parsed.get("error") or "not a booking document",
            ),
        )
        report.suggested_action = "reject_document"

    status, message = _status_for(report, doc_ok)
    sid = session_id or str(uuid.uuid4())
    backend = parsed.get("backend")
    history = [
        {
            "at": _now(),
            "action": "parse_validate",
            "actor": "llm",
            "detail": {
                "overall": report.overall,
                "backend": backend,
                "has_llm_analysis": bool(llm_analysis),
                "mix_diff_count": len(mix_raw),
            },
        }
    ]
    meta: dict[str, Any] = {
        "doc_type_ok": doc_ok,
        "backend": backend,
        "fields": {
            k: {"source": "llm"} for k, v in (validated or {}).items() if v is not None
        },
    }
    if parsed.get("html_struct_raw") is not None:
        meta["html_struct_raw"] = parsed["html_struct_raw"]
    if parsed.get("form_family"):
        meta["form_family"] = parsed["form_family"]
    if mix_raw:
        meta["mix_diff_fields"] = [i.get("field") for i in mix_raw]
    metrics_stub("parse_booking", overall=report.overall)
    record = BookingRecord(
        session_id=sid,
        status=status,
        message=message,
        filename=filename,
        raw_extracted_data=raw,
        normalized_data=normalized,
        llm_analysis=llm_analysis,
        validated_data=validated,
        validation_report=report,
        meta=meta,
        history=history,
    )
    _dump_parse_debug(record=record, parsed=parsed, filename=filename)
    return record


def triple_from_record(record: BookingRecord) -> dict[str, Any]:
    """从 BookingRecord 投影 HTTP/MCP 扁平字段（含 raw / normalized / analysis）。"""
    report = record.validation_report
    return {
        "raw_extracted_data": record.raw_extracted_data,
        "normalized_data": record.normalized_data,
        "llm_analysis": record.llm_analysis,
        "validated_data": record.validated_data,
        "validation_report": report.model_dump() if report else None,
        "doc_type_ok": bool((record.meta or {}).get("doc_type_ok", True)),
        "filename": record.filename,
        "backend": (record.meta or {}).get("backend"),
    }
