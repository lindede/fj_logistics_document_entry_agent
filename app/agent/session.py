from __future__ import annotations

from typing import Any, Optional

from app.agent.graph import (
    get_session_values,
    open_session,
    resume_session,
    session_is_waiting,
)
from app.agent.intents import detect_intent, parse_nl_patches
from app.booking import process_booking, triple_from_record
from app.booking.feedback import save_pending_source
from app.config import SUBMIT_STRATEGY
from app.observe import timed, trace_stub
from app.parse.pdf_io import resolve_pdf_input


class SessionManager:
    """薄封装：会话真相在 LangGraph；对外只暴露 session_id（= checkpoint thread）。"""

    def __init__(self) -> None:
        self.session_id: Optional[str] = None
        self._pending_replace: Optional[dict[str, Any]] = None
        self.submit_strategy = SUBMIT_STRATEGY

    def _values(self) -> dict[str, Any]:
        if not self.session_id:
            return {}
        return get_session_values(self.session_id)

    def snapshot(self) -> dict[str, Any]:
        pending = bool(self._pending_replace)
        vals = self._values()
        if not self.session_id or not vals:
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
                "replace_pending": pending,
            }
        return {
            "session_id": vals.get("session_id") or self.session_id,
            "status": vals.get("status") or "Idle",
            "message": vals.get("message"),
            "raw_extracted_data": vals.get("raw_extracted_data"),
            "validated_data": vals.get("validated_data"),
            "validation_report": vals.get("validation_report"),
            "meta": vals.get("meta") or {},
            "history": list(vals.get("history") or []),
            "filename": vals.get("filename"),
            "submit_strategy": self.submit_strategy,
            "replace_pending": pending,
            "graph_waiting": session_is_waiting(self.session_id),
        }

    @property
    def record(self) -> Any:
        """兼容旧测试：从 graph state 投影常用字段。"""
        vals = self._values()
        if not self.session_id:
            return None

        class _R:
            pass

        r = _R()
        r.session_id = vals.get("session_id") or self.session_id
        r.status = vals.get("status") or "Idle"
        r.message = vals.get("message")
        r.filename = vals.get("filename")
        r.raw_extracted_data = vals.get("raw_extracted_data")
        r.validated_data = vals.get("validated_data")
        report = vals.get("validation_report")
        if report:
            from app.models import ValidationReport

            r.validation_report = ValidationReport(**report)
        else:
            r.validation_report = None
        r.meta = vals.get("meta") or {}
        r.history = list(vals.get("history") or [])
        return r

    @timed("parse_and_validate")
    def parse_and_validate(
        self, file_path: str | None = None, base64_pdf: str | None = None
    ) -> dict[str, Any]:
        """无会话 Tool/API：不经线程，直接 process_booking。"""
        trace_stub("parse_and_validate")
        record = process_booking(file_path=file_path, base64_pdf=base64_pdf)
        return triple_from_record(record)

    def open_booking(
        self, file_path: str | None = None, base64_pdf: str | None = None
    ) -> dict[str, Any]:
        pdf_bytes, filename = resolve_pdf_input(file_path, base64_pdf)
        sid = open_session(
            submit_strategy=self.submit_strategy,
            file_path=file_path,
            base64_pdf=base64_pdf,
        )
        self.session_id = sid
        save_pending_source(sid, pdf_bytes, filename)
        return self.snapshot()

    def patch_fields(
        self, patches: dict[str, Any], actor: str = "human"
    ) -> dict[str, Any]:
        if not self.session_id or not session_is_waiting(self.session_id):
            return {**self.snapshot(), "message": "当前无进行中的单据可修改"}
        vals = self._values()
        if not vals.get("validated_data"):
            return {**self.snapshot(), "message": "当前无进行中的单据可修改"}
        resume_session(
            self.session_id,
            action="patch",
            patches=dict(patches),
            actor=actor,
        )
        return self.snapshot()

    def submit(self) -> dict[str, Any]:
        if not self.session_id or not session_is_waiting(self.session_id):
            return {**self.snapshot(), "message": "当前状态不可提交"}
        vals = self._values()
        status = vals.get("status")
        if status not in {"AwaitConfirm", "AwaitHuman"}:
            return {**self.snapshot(), "message": "当前状态不可提交"}
        report = vals.get("validation_report") or {}
        if report.get("overall") == "FAIL":
            return {**self.snapshot(), "message": "存在 FAIL，请先修正再提交"}
        resume_session(self.session_id, action="submit", actor="human")
        return self.snapshot()

    def void(self) -> dict[str, Any]:
        if not self.session_id or not session_is_waiting(self.session_id):
            return {**self.snapshot(), "message": "无进行中的单据"}
        resume_session(self.session_id, action="void", actor="human")
        vals = self._values()
        hist = list(vals.get("history") or [])
        self.session_id = None
        self._pending_replace = None
        return {
            "session_id": None,
            "status": "Idle",
            "message": vals.get("message") or "已作废，可开新票",
            "raw_extracted_data": None,
            "validated_data": None,
            "validation_report": None,
            "meta": {},
            "history": hist,
            "filename": None,
            "submit_strategy": self.submit_strategy,
            "replace_pending": False,
        }

    def handle(
        self,
        *,
        action: str | None = None,
        text: str | None = None,
        file_path: str | None = None,
        base64_pdf: str | None = None,
        patches: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        vals = self._values()
        status = "Idle"
        if self.session_id and vals:
            status = vals.get("status") or "Idle"

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
                    "message": "当前有进行中的单据，请确认是否换票",
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
                "message": "当前有进行中的单据，请确认是否换票",
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


session_manager = SessionManager()
