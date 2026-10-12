from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.agent.intents import (
    apply_weight_unit_conversion,
    detect_intent,
    parse_nl_patches,
)
from app.config import FEEDBACK_DIR, STORE_DIR, SUBMIT_STRATEGY
from app.models import BookingRecord, ValidationReport
from app.observe import metrics_stub, timed, trace_stub
from app.parse.extract import parse_pdf_bytes
from app.parse.pdf_io import resolve_pdf_input
from app.parse.schema_fill import fill_schema
from app.validate import validate_booking


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionManager:
    """单进程一票会话（M-AGT）。"""

    def __init__(self) -> None:
        self.record: Optional[BookingRecord] = None
        self._pending_replace: Optional[dict[str, Any]] = None
        self.submit_strategy = SUBMIT_STRATEGY

    def snapshot(self) -> dict[str, Any]:
        if not self.record:
            return {
                "session_id": None,
                "status": "Idle",
                "message": "拖入 PDF 或输入开票指令开始",
                "raw_extracted_data": None,
                "validated_data": None,
                "validation_report": None,
                "meta": {},
                "history": [],
                "filename": None,
                "submit_strategy": self.submit_strategy,
            }
        return self.record.model_dump()

    def _hist(self, action: str, actor: str, detail: Any = None) -> None:
        assert self.record is not None
        self.record.history.append(
            {"at": _now(), "action": action, "actor": actor, "detail": detail}
        )

    def _meta_sources(self, data: dict[str, Any], source: str) -> dict[str, Any]:
        fields = {}
        for k, v in data.items():
            if v is None and source == "llm":
                fields[k] = {"source": "schema"}
            else:
                fields[k] = {"source": source}
        return {"fields": fields}

    def _route_after_validation(self) -> None:
        assert self.record and self.record.validation_report
        report = self.record.validation_report
        overall = report.overall
        if overall == "FAIL" or report.low_confidence_fields:
            self.record.status = "AwaitHuman"
            self.record.message = "校验未通过或低置信，请修正后重验或作废"
        elif overall == "WARN":
            self.record.status = "AwaitConfirm"
            self.record.message = "存在警告，请确认后提交或修改"
        else:
            if self.submit_strategy == "auto_on_pass":
                self._persist("system")
                self.record.status = "Idle"
                self.record.message = "校验通过，已自动提交"
                # 保留一拍完成提示：history 已有；清空业务数据但可查 history
                sid = self.record.session_id
                hist = list(self.record.history)
                self.record = BookingRecord(
                    session_id=sid,
                    status="Idle",
                    message="已自动提交，可开新票",
                    history=hist,
                    meta={},
                )
            else:
                self.record.status = "AwaitConfirm"
                self.record.message = "校验通过，请确认提交"

    @timed("parse_and_validate")
    def parse_and_validate(
        self, file_path: str | None = None, base64_pdf: str | None = None
    ) -> dict[str, Any]:
        trace_stub("parse_and_validate")
        pdf_bytes, filename = resolve_pdf_input(file_path, base64_pdf)
        parsed = parse_pdf_bytes(pdf_bytes)
        raw = parsed["raw_extracted_data"]
        conf = parsed["field_confidence"]
        from app.models import FieldIssue

        validated, report = validate_booking(raw, conf)
        if not parsed["doc_type_ok"]:
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

        result = {
            "raw_extracted_data": raw,
            "validated_data": validated,
            "validation_report": report.model_dump(),
            "doc_type_ok": parsed["doc_type_ok"],
            "filename": filename,
            "backend": parsed.get("backend"),
        }
        metrics_stub("parse_booking", overall=report.overall)
        return result

    def open_booking(
        self, file_path: str | None = None, base64_pdf: str | None = None
    ) -> dict[str, Any]:
        self.record = BookingRecord(
            session_id=str(uuid.uuid4()),
            status="Parsing",
            message="解析中…",
            filename=None,
        )
        self._hist("open_booking", "human", {"file_path": file_path})
        self.record.status = "Validating"
        self.record.message = "校验中…"
        result = self.parse_and_validate(file_path, base64_pdf)
        self.record.filename = result.get("filename")
        self.record.raw_extracted_data = result["raw_extracted_data"]
        self.record.validated_data = result["validated_data"]
        self.record.validation_report = ValidationReport(
            **result["validation_report"]
        )
        self.record.meta = self._meta_sources(result["raw_extracted_data"], "llm")
        self._hist(
            "parse_validate",
            "llm",
            {
                "overall": self.record.validation_report.overall,
                "backend": result.get("backend"),
            },
        )
        if not result.get("doc_type_ok"):
            self.record.status = "AwaitHuman"
            self.record.message = "单据类型不是托运/订舱单"
        else:
            self._route_after_validation()
        return self.snapshot()

    def patch_fields(
        self, patches: dict[str, Any], actor: str = "human"
    ) -> dict[str, Any]:
        if not self.record or not self.record.validated_data:
            return {**self.snapshot(), "message": "当前无进行中的单据可修改"}
        self.record.status = "Validating"
        data = fill_schema(self.record.validated_data)
        convert = bool(patches.pop("_convert_weight", False))
        if convert and "weight_unit" in patches:
            data = apply_weight_unit_conversion(data, str(patches["weight_unit"]))
            patches = {**patches, "gross_weight": data.get("gross_weight")}
        for k, v in patches.items():
            data[k] = v
            if self.record.meta.get("fields") is None:
                self.record.meta["fields"] = {}
            self.record.meta.setdefault("fields", {})[k] = {"source": actor}
        conf = (
            self.record.validation_report.field_confidence
            if self.record.validation_report
            else {}
        )
        # 人改字段抬高置信
        for k in patches:
            conf[k] = 0.95
        validated, report = validate_booking(data, conf)
        self.record.validated_data = validated
        self.record.validation_report = report
        self._hist("patch_fields", actor, {"patches": patches, "overall": report.overall})
        self._route_after_validation()
        return self.snapshot()

    def _persist(self, actor: str) -> Path:
        assert self.record
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        path = STORE_DIR / f"{self.record.session_id}.json"
        payload = self.record.model_dump()
        payload["submitted_at"] = _now()
        payload["submitted_by"] = actor
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._hist("submit", actor, {"path": str(path)})
        # VAL-07 占位：可回流目录
        FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        fb = FEEDBACK_DIR / f"{self.record.session_id}.json"
        fb.write_text(
            json.dumps(
                {
                    "validated_data": self.record.validated_data,
                    "meta": self.record.meta,
                    "note": "placeholder for human-corrected gold reflux (VAL-07)",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def submit(self) -> dict[str, Any]:
        if not self.record or self.record.status not in {
            "AwaitConfirm",
            "AwaitHuman",
        }:
            return {**self.snapshot(), "message": "当前状态不可提交"}
        if (
            self.record.validation_report
            and self.record.validation_report.overall == "FAIL"
        ):
            return {**self.snapshot(), "message": "存在 FAIL，请先修正再提交"}
        self._persist("human")
        hist = list(self.record.history)
        sid = self.record.session_id
        self.record = BookingRecord(
            session_id=sid,
            status="Idle",
            message="已提交，可开新票",
            history=hist,
            meta={},
        )
        return self.snapshot()

    def void(self) -> dict[str, Any]:
        if not self.record or self.record.status == "Idle":
            return {**self.snapshot(), "message": "无进行中的单据"}
        self._hist("void", "human", {})
        hist = list(self.record.history)
        self.record = BookingRecord(
            session_id=str(uuid.uuid4()),
            status="Idle",
            message="已作废，可开新票",
            history=hist,
            meta={},
        )
        self._pending_replace = None
        return self.snapshot()

    def handle(
        self,
        *,
        action: str | None = None,
        text: str | None = None,
        file_path: str | None = None,
        base64_pdf: str | None = None,
        patches: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = self.record.status if self.record else "Idle"
        has_pdf = bool(file_path or base64_pdf)

        if action in {"status", "snapshot"}:
            return self.snapshot()
        if action == "submit":
            return self.submit()
        if action == "void":
            return self.void()
        if action == "confirm_replace" and self._pending_replace:
            pending = self._pending_replace
            self._pending_replace = None
            self.void()
            return self.open_booking(
                pending.get("file_path"), pending.get("base64_pdf")
            )
        if action == "cancel_replace":
            self._pending_replace = None
            return {**self.snapshot(), "message": "已取消换票"}
        if action == "patch" and patches:
            return self.patch_fields(patches, actor="human")
        if action == "open" and has_pdf:
            if status != "Idle":
                self._pending_replace = {
                    "file_path": file_path,
                    "base64_pdf": base64_pdf,
                }
                return {
                    **self.snapshot(),
                    "message": "当前有进行中的单据，确认换票？发送「换票」或 action=confirm_replace",
                    "replace_pending": True,
                }
            return self.open_booking(file_path, base64_pdf)

        intent = detect_intent(
            text, has_pdf=has_pdf, patches=patches, status=status
        )
        if intent == "open_booking":
            return self.open_booking(file_path, base64_pdf)
        if intent == "replace_conflict":
            self._pending_replace = {"file_path": file_path, "base64_pdf": base64_pdf}
            return {
                **self.snapshot(),
                "message": "当前有进行中的单据，确认换票？请回复「换票」",
                "replace_pending": True,
            }
        if intent == "replace_confirm" and self._pending_replace:
            pending = self._pending_replace
            self._pending_replace = None
            self.void()
            if pending.get("file_path") or pending.get("base64_pdf"):
                return self.open_booking(
                    pending.get("file_path"), pending.get("base64_pdf")
                )
            return {**self.snapshot(), "message": "已结束当前票，请上传新 PDF"}
        if intent == "submit":
            return self.submit()
        if intent == "void":
            return self.void()
        if intent == "patch_fields" and patches:
            return self.patch_fields(patches, actor="human")
        if intent == "nl_patch":
            if status == "Idle":
                return {
                    **self.snapshot(),
                    "message": "当前空闲，是否先开票？请上传 PDF",
                }
            nl = parse_nl_patches(text or "")
            if not nl:
                return {**self.snapshot(), "message": "未能理解改数字指令"}
            return self.patch_fields(nl, actor="human")
        if intent == "open_need_pdf":
            return {**self.snapshot(), "message": "开票需要 PDF，请拖入文件"}
        if intent == "noop":
            return self.snapshot()
        return {**self.snapshot(), "message": f"未识别指令：{text}"}


# 模块级单例
session_manager = SessionManager()
