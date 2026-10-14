from __future__ import annotations

from typing import Any, Optional

from app.agent.amend_llm import run_done_amend_from_text
from app.agent.graph import (
    get_session_values,
    open_session,
    resume_session,
    session_is_waiting,
    sync_done_state,
)
from app.agent.intents import detect_intent
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
        # Done 修正失败时的只读预览（不落盘）
        self._amend_preview: Optional[dict[str, Any]] = None

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
                "normalized_data": None,
                "llm_analysis": None,
                "validated_data": None,
                "validation_report": None,
                "meta": {},
                "history": [],
                "filename": None,
                "submit_strategy": self.submit_strategy,
                "replace_pending": pending,
                "composer_mode": "hidden",
                "highlight_fields": [],
                "error_fields": [],
            }
        status = vals.get("status") or "Idle"
        out = {
            "session_id": vals.get("session_id") or self.session_id,
            "status": status,
            "message": vals.get("message"),
            "raw_extracted_data": vals.get("raw_extracted_data"),
            "normalized_data": vals.get("normalized_data"),
            "llm_analysis": vals.get("llm_analysis"),
            "validated_data": vals.get("validated_data"),
            "validation_report": vals.get("validation_report"),
            "meta": vals.get("meta") or {},
            "history": list(vals.get("history") or []),
            "filename": vals.get("filename"),
            "submit_strategy": self.submit_strategy,
            "replace_pending": pending,
            "graph_waiting": session_is_waiting(self.session_id),
            "composer_mode": "done_amend" if status == "Done" else "hidden",
            "highlight_fields": [],
            "error_fields": [],
        }
        if status == "Done" and self._amend_preview:
            prev = self._amend_preview
            if prev.get("validated_data") is not None:
                out["validated_data"] = prev["validated_data"]
            if prev.get("validation_report") is not None:
                out["validation_report"] = prev["validation_report"]
            if prev.get("message"):
                out["message"] = prev["message"]
            out["highlight_fields"] = list(prev.get("changed_fields") or [])
            out["error_fields"] = list(prev.get("error_fields") or [])
            out["amend_written"] = bool(prev.get("written"))
            out["amend_ok"] = bool(prev.get("written"))
            if prev.get("understood") is not None:
                out["understood"] = prev.get("understood")
            if prev.get("amend_trace") is not None:
                out["amend_trace"] = prev.get("amend_trace")
        return out

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
        r.normalized_data = vals.get("normalized_data")
        r.llm_analysis = vals.get("llm_analysis")
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
        self._amend_preview = None
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

    def submit(self, *, force: bool = False) -> dict[str, Any]:
        if not self.session_id or not session_is_waiting(self.session_id):
            return {**self.snapshot(), "message": "当前状态不可提交"}
        vals = self._values()
        status = vals.get("status")
        if status not in {"AwaitConfirm", "AwaitHuman"}:
            return {**self.snapshot(), "message": "当前状态不可提交"}
        report = vals.get("validation_report") or {}
        overall = report.get("overall")
        if overall in {"FAIL", "WARN"} and not force:
            return {
                **self.snapshot(),
                "message": f"存在 {overall}，请修正后提交，或使用强制提交",
            }
        actor = "human_force" if force else "human"
        resume_session(self.session_id, action="submit", actor=actor)
        return self.snapshot()

    def void(self) -> dict[str, Any]:
        if not self.session_id or not session_is_waiting(self.session_id):
            return {**self.snapshot(), "message": "无进行中的单据"}
        resume_session(self.session_id, action="void", actor="human")
        vals = self._values()
        hist = list(vals.get("history") or [])
        self.session_id = None
        self._pending_replace = None
        self._amend_preview = None
        return {
            "session_id": None,
            "status": "Idle",
            "message": vals.get("message") or "已作废，可开新票",
            "raw_extracted_data": None,
            "normalized_data": None,
            "llm_analysis": None,
            "validated_data": None,
            "validation_report": None,
            "meta": {},
            "history": hist,
            "filename": None,
            "submit_strategy": self.submit_strategy,
            "replace_pending": False,
            "composer_mode": "hidden",
            "highlight_fields": [],
            "error_fields": [],
        }

    def handle(
        self,
        *,
        action: str | None = None,
        text: str | None = None,
        file_path: str | None = None,
        base64_pdf: str | None = None,
        patches: dict[str, Any] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        vals = self._values()
        status = "Idle"
        if self.session_id and vals:
            status = vals.get("status") or "Idle"

        has_pdf = bool(file_path or base64_pdf)

        if action in {"status", "snapshot"}:
            return self.snapshot()
        if action == "submit":
            return self.submit(force=force)
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
            # Idle / Done：直接开新票；进行中才需确认放弃
            if status not in {"Idle", "Done"}:
                self._pending_replace = {
                    "file_path": file_path,
                    "base64_pdf": base64_pdf,
                }
                return {
                    **self.snapshot(),
                    "message": "当前有进行中的单据，请确认是否放弃",
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
                "message": "当前有进行中的单据，请确认是否放弃",
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
            return self._amend_done_from_chat(text or "", status=status, vals=vals)
        if intent == "open_need_pdf":
            return {**self.snapshot(), "message": "开票需要 PDF，请拖入文件"}
        if intent == "noop":
            return self.snapshot()
        return {**self.snapshot(), "message": f"未识别指令：{text}"}

    def _amend_done_from_chat(
        self,
        text: str,
        *,
        status: str,
        vals: dict[str, Any],
    ) -> dict[str, Any]:
        """仅 Done：LLM tool / 正则 → amend_booking_record（先验后写）。"""
        if status != "Done" or not self.session_id:
            return {
                **self.snapshot(),
                "message": "文字修正仅在提交完成（Done）后可用；录入中请直接改表单",
            }
        # 预览失败时以预览数据为当前上下文，便于连续修正
        current = (self._amend_preview or {}).get("validated_data") or vals.get(
            "validated_data"
        ) or {}
        result = run_done_amend_from_text(
            self.session_id, text, current=current
        )
        preview = {
            "validated_data": result.get("validated_data") or current,
            "validation_report": result.get("validation_report"),
            "changed_fields": result.get("changed_fields") or [],
            "error_fields": result.get("error_fields") or [],
            "message": result.get("message"),
            "written": bool(result.get("written")),
            "understood": result.get("understood"),
            "amend_trace": result.get("amend_trace"),
        }
        self._amend_preview = preview
        if result.get("written"):
            rec = result.get("record") or {}
            sync_done_state(
                self.session_id,
                validated_data=result.get("validated_data"),
                validation_report=result.get("validation_report"),
                history=list(rec.get("history") or vals.get("history") or []),
                message=result.get("message"),
                normalized_data=result.get("validated_data"),
            )
        snap = self.snapshot()
        snap["message"] = result.get("message") or snap.get("message")
        snap["amend_written"] = bool(result.get("written"))
        snap["amend_ok"] = bool(result.get("ok"))
        snap["understood"] = result.get("understood")
        snap["amend_trace"] = result.get("amend_trace")
        return snap


session_manager = SessionManager()
