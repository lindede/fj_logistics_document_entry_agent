"""LangGraph 为会话唯一状态源。

业务侧只认 session_id。LangGraph 要求的 configurable.thread_id
仅在 _cfg() 中等于 session_id，禁止另起一套 ID。

拓扑：
  START → parse → validate → route → (auto? submit : wait_human)
  wait_human —patch→ apply_patches → validate → route → …
             —submit→ submit → END
             —void→ void → END
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent.intents import apply_weight_unit_conversion
from app.booking.feedback import discard_pending, promote_or_discard
from app.config import STORE_DIR
from app.models import BookingRecord, ValidationReport
from app.parse.schema_fill import fill_schema
from app.tools.parse_booking_client import invoke_parse_booking
from app.validate import validate_booking


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BookingGraphState(TypedDict, total=False):
    session_id: str
    submit_strategy: str
    file_path: Optional[str]
    base64_pdf: Optional[str]
    filename: Optional[str]
    status: str
    message: str
    raw_extracted_data: Optional[dict[str, Any]]
    normalized_data: Optional[dict[str, Any]]
    llm_analysis: Optional[str]
    validated_data: Optional[dict[str, Any]]
    validation_report: Optional[dict[str, Any]]
    field_confidence: dict[str, float]
    doc_type_ok: bool
    backend: Optional[str]
    parse_error: Optional[str]
    meta: dict[str, Any]
    history: list[dict[str, Any]]
    patches: dict[str, Any]
    actor: str
    pending_action: Optional[str]
    auto_submitted: bool
    graph_path: list[str]
    phase: Literal["open", "revalidate"]


def _cfg(session_id: str) -> dict[str, Any]:
    """唯一映射：session_id → LangGraph thread_id（二者同值）。"""
    return {"configurable": {"thread_id": session_id}}


def _append_hist(
    state: BookingGraphState, action: str, actor: str, detail: Any = None
) -> list[dict[str, Any]]:
    hist = list(state.get("history") or [])
    hist.append({"at": _now(), "action": action, "actor": actor, "detail": detail})
    return hist


def _meta_sources(data: dict[str, Any], source: str) -> dict[str, Any]:
    fields = {}
    for k, v in data.items():
        if v is None and source == "llm":
            fields[k] = {"source": "schema"}
        else:
            fields[k] = {"source": source}
    return {"fields": fields}


def node_parse(state: BookingGraphState) -> dict[str, Any]:
    """开票：经 parse_booking Tool（HTTP 或本地门面），不直连 extract。"""
    path = list(state.get("graph_path") or []) + ["parse"]
    tool = invoke_parse_booking(
        file_path=state.get("file_path"),
        base64_pdf=state.get("base64_pdf"),
    )
    raw = tool.get("raw_extracted_data") or {}
    normalized = tool.get("normalized_data") or raw
    llm_analysis = tool.get("llm_analysis")
    report = tool.get("validation_report") or {}
    conf = {}
    if isinstance(report, dict):
        conf = dict(report.get("field_confidence") or {})
    hist = _append_hist(
        state, "open_booking", "human", {"file_path": state.get("file_path")}
    )
    hist.append(
        {
            "at": _now(),
            "action": "parse_validate",
            "actor": "tool",
            "detail": {
                "overall": report.get("overall") if isinstance(report, dict) else None,
                "via": "parse_booking_tool",
                "has_llm_analysis": bool(llm_analysis),
            },
        }
    )
    seed = tool.get("validated_data") or normalized
    return {
        "graph_path": path,
        "phase": "open",
        "status": "Validating",
        "message": "校验中…",
        "filename": tool.get("filename"),
        "raw_extracted_data": raw,
        "normalized_data": normalized,
        "llm_analysis": llm_analysis,
        "validated_data": seed,
        "validation_report": report,
        "field_confidence": conf,
        "doc_type_ok": bool(tool.get("doc_type_ok", True)),
        "backend": tool.get("backend"),
        "parse_error": None,
        "history": hist,
        "meta": _meta_sources(normalized, "llm"),
        "auto_submitted": False,
        "pending_action": None,
    }


def node_apply_patches(state: BookingGraphState) -> dict[str, Any]:
    path = list(state.get("graph_path") or []) + ["apply_patches"]
    patches = dict(state.get("patches") or {})
    actor = state.get("actor") or "human"
    data = fill_schema(state.get("validated_data") or {})
    convert = bool(patches.pop("_convert_weight", False))
    if convert and "weight_unit" in patches:
        data = apply_weight_unit_conversion(data, str(patches["weight_unit"]))
        patches = {**patches, "gross_weight": data.get("gross_weight")}

    meta = dict(state.get("meta") or {})
    fields = dict(meta.get("fields") or {})
    for k, v in patches.items():
        data[k] = v
        fields[k] = {"source": actor}
    meta["fields"] = fields
    if actor == "human":
        meta["human_touched"] = True

    conf = dict(state.get("field_confidence") or {})
    report = state.get("validation_report") or {}
    if not conf and isinstance(report, dict):
        conf = dict(report.get("field_confidence") or {})
    for k in patches:
        conf[k] = 0.95

    hist = _append_hist(state, "patch_fields", actor, {"patches": patches})
    return {
        "graph_path": path,
        "phase": "revalidate",
        "status": "Validating",
        "message": "校验中…",
        "validated_data": data,
        # raw / normalized / analysis：解析快照，patch 不改写
        "raw_extracted_data": state.get("raw_extracted_data"),
        "normalized_data": state.get("normalized_data"),
        "llm_analysis": state.get("llm_analysis"),
        "field_confidence": conf,
        "meta": meta,
        "history": hist,
        "patches": patches,
        "doc_type_ok": True,
        "auto_submitted": False,
    }


def node_validate(state: BookingGraphState) -> dict[str, Any]:
    path = list(state.get("graph_path") or []) + ["validate"]
    phase = state.get("phase") or "open"
    # 开票已由 parse_booking Tool 带齐三件套，此处不再本地重跑解析侧校验
    if phase == "open" and state.get("validation_report"):
        return {"graph_path": path}

    data = (
        state.get("validated_data")
        or state.get("normalized_data")
        or state.get("raw_extracted_data")
        or {}
    )
    conf = dict(state.get("field_confidence") or {})
    validated, report = validate_booking(data, conf)

    hist = _append_hist(
        state,
        "revalidate",
        state.get("actor") or "human",
        {"overall": report.overall, "backend": state.get("backend")},
    )
    return {
        "graph_path": path,
        "validated_data": validated,
        "validation_report": report.model_dump(),
        "field_confidence": report.field_confidence,
        "history": hist,
    }


def node_route(state: BookingGraphState) -> dict[str, Any]:
    path = list(state.get("graph_path") or []) + ["route"]
    report_raw = state.get("validation_report") or {}
    report = ValidationReport(**report_raw) if report_raw else None
    phase = state.get("phase") or "open"

    if phase == "open" and not state.get("doc_type_ok", True):
        return {
            "graph_path": path,
            "status": "AwaitHuman",
            "message": "单据类型不是托运/订舱单",
            "auto_submitted": False,
        }
    if not report:
        return {
            "graph_path": path,
            "status": "AwaitHuman",
            "message": "缺少校验报告",
            "auto_submitted": False,
        }

    overall = report.overall
    strategy = (state.get("submit_strategy") or "manual").lower()
    if overall == "FAIL" or report.low_confidence_fields:
        return {
            "graph_path": path,
            "status": "AwaitHuman",
            "message": "校验未通过或低置信，请修正后重验或作废",
            "auto_submitted": False,
        }
    if overall == "WARN":
        return {
            "graph_path": path,
            "status": "AwaitConfirm",
            "message": "存在警告，请确认后提交或修改",
            "auto_submitted": False,
        }
    if strategy == "auto_on_pass":
        return {
            "graph_path": path,
            "status": "Idle",
            "message": "校验通过，已自动提交",
            "auto_submitted": True,
        }
    return {
        "graph_path": path,
        "status": "AwaitConfirm",
        "message": "校验通过，请确认提交",
        "auto_submitted": False,
    }


def _as_record(state: BookingGraphState) -> BookingRecord:
    report_raw = state.get("validation_report")
    report = ValidationReport(**report_raw) if report_raw else None
    return BookingRecord(
        session_id=state.get("session_id") or "",
        status=state.get("status") or "Idle",
        message=state.get("message"),
        filename=state.get("filename"),
        raw_extracted_data=state.get("raw_extracted_data"),
        normalized_data=state.get("normalized_data"),
        llm_analysis=state.get("llm_analysis"),
        validated_data=state.get("validated_data"),
        validation_report=report,
        meta=state.get("meta") or {},
        history=list(state.get("history") or []),
    )


def node_submit(state: BookingGraphState) -> dict[str, Any]:
    path = list(state.get("graph_path") or []) + ["submit"]
    actor = "system" if state.get("auto_submitted") else (state.get("actor") or "human")
    record = _as_record(state)

    STORE_DIR.mkdir(parents=True, exist_ok=True)
    store_path = STORE_DIR / f"{record.session_id}.json"
    payload = record.model_dump()
    payload["submitted_at"] = _now()
    payload["submitted_by"] = actor
    store_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fb = promote_or_discard(record, actor=actor)
    hist = _append_hist(
        state, "submit", actor, {"path": str(store_path), "feedback": fb}
    )
    msg = (
        "已自动提交，可开新票"
        if state.get("auto_submitted")
        else "已提交，可开新票"
    )
    return {
        "graph_path": path,
        "status": "Idle",
        "message": msg,
        "raw_extracted_data": None,
        "normalized_data": None,
        "llm_analysis": None,
        "validated_data": None,
        "validation_report": None,
        "meta": {},
        "history": hist,
        "auto_submitted": False,
        "pending_action": None,
        "patches": {},
    }


def node_void(state: BookingGraphState) -> dict[str, Any]:
    path = list(state.get("graph_path") or []) + ["void"]
    sid = state.get("session_id") or ""
    discard_pending(sid)
    hist = _append_hist(state, "void", "human", {})
    # 不改 session_id：与 checkpoint thread 保持同一值；下一票 open 再发新 id
    return {
        "graph_path": path,
        "status": "Idle",
        "message": "已作废，可开新票",
        "raw_extracted_data": None,
        "normalized_data": None,
        "llm_analysis": None,
        "validated_data": None,
        "validation_report": None,
        "meta": {},
        "history": hist,
        "auto_submitted": False,
        "pending_action": None,
        "patches": {},
    }


def node_wait_human(state: BookingGraphState) -> dict[str, Any]:
    """挂起等人：patch / submit / void。"""
    path = list(state.get("graph_path") or []) + ["wait_human"]
    decision = interrupt(
        {
            "status": state.get("status"),
            "message": state.get("message"),
            "session_id": state.get("session_id"),
        }
    )
    action = (decision or {}).get("action") or "noop"
    patches = dict((decision or {}).get("patches") or {})
    actor = (decision or {}).get("actor") or "human"
    return {
        "graph_path": path,
        "pending_action": action,
        "patches": patches,
        "actor": actor,
    }


def _after_route(state: BookingGraphState) -> str:
    if state.get("auto_submitted"):
        return "submit"
    return "wait_human"


def _after_wait(state: BookingGraphState) -> str:
    action = state.get("pending_action") or "noop"
    if action == "patch":
        return "apply_patches"
    if action == "submit":
        return "submit"
    if action == "void":
        return "void"
    return "wait_human"


def build_booking_graph():
    g = StateGraph(BookingGraphState)
    g.add_node("parse", node_parse)
    g.add_node("apply_patches", node_apply_patches)
    g.add_node("validate", node_validate)
    g.add_node("route", node_route)
    g.add_node("wait_human", node_wait_human)
    g.add_node("submit", node_submit)
    g.add_node("void", node_void)

    g.add_edge(START, "parse")
    g.add_edge("parse", "validate")
    g.add_edge("validate", "route")
    g.add_conditional_edges(
        "route", _after_route, {"submit": "submit", "wait_human": "wait_human"}
    )
    g.add_conditional_edges(
        "wait_human",
        _after_wait,
        {
            "apply_patches": "apply_patches",
            "submit": "submit",
            "void": "void",
            "wait_human": "wait_human",
        },
    )
    g.add_edge("apply_patches", "validate")
    g.add_edge("submit", END)
    g.add_edge("void", END)

    return g.compile(checkpointer=MemorySaver())


booking_graph = build_booking_graph()


def open_session(
    *,
    submit_strategy: str,
    file_path: str | None = None,
    base64_pdf: str | None = None,
    session_id: str | None = None,
) -> str:
    """开新票：新建 session_id（兼作 LangGraph thread），跑到 wait_human 或 auto submit。"""
    sid = session_id or str(uuid.uuid4())
    booking_graph.invoke(
        {
            "session_id": sid,
            "submit_strategy": submit_strategy,
            "file_path": file_path,
            "base64_pdf": base64_pdf,
            "status": "Parsing",
            "message": "解析中…",
            "history": [],
            "meta": {},
            "graph_path": [],
            "auto_submitted": False,
            "doc_type_ok": True,
            "phase": "open",
            "pending_action": None,
        },
        config=_cfg(sid),
    )
    return sid


def resume_session(
    session_id: str,
    *,
    action: str,
    patches: dict[str, Any] | None = None,
    actor: str = "human",
) -> None:
    """在同一 session（同一 checkpoint thread）上 resume wait_human。"""
    booking_graph.invoke(
        Command(
            resume={
                "action": action,
                "patches": patches or {},
                "actor": actor,
            }
        ),
        config=_cfg(session_id),
    )


def get_session_values(session_id: str) -> dict[str, Any]:
    snap = booking_graph.get_state(_cfg(session_id))
    return dict(snap.values or {})


def session_is_waiting(session_id: str) -> bool:
    snap = booking_graph.get_state(_cfg(session_id))
    return bool(snap.next)

