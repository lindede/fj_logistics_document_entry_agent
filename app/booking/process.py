from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.models import BookingRecord, FieldIssue, ValidationReport
from app.observe import metrics_stub
from app.parse.extract import parse_pdf_bytes
from app.parse.pdf_io import resolve_pdf_input
from app.validate import validate_booking


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    conf = parsed["field_confidence"]
    doc_ok = bool(parsed.get("doc_type_ok", True))

    validated, report = validate_booking(raw, conf)
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
            "detail": {"overall": report.overall, "backend": backend},
        }
    ]
    meta: dict[str, Any] = {
        "doc_type_ok": doc_ok,
        "backend": backend,
        "fields": {
            k: {"source": "llm"} for k, v in (validated or {}).items() if v is not None
        },
    }
    metrics_stub("parse_booking", overall=report.overall)
    return BookingRecord(
        session_id=sid,
        status=status,
        message=message,
        filename=filename,
        raw_extracted_data=raw,
        validated_data=validated,
        validation_report=report,
        meta=meta,
        history=history,
    )


def triple_from_record(record: BookingRecord) -> dict[str, Any]:
    """从 BookingRecord 投影 HTTP/MCP 扁平三件套。"""
    report = record.validation_report
    return {
        "raw_extracted_data": record.raw_extracted_data,
        "validated_data": record.validated_data,
        "validation_report": report.model_dump() if report else None,
        "doc_type_ok": bool((record.meta or {}).get("doc_type_ok", True)),
        "filename": record.filename,
        "backend": (record.meta or {}).get("backend"),
    }
