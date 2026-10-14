"""Done 态：LLM Function Calling → amend_booking_record。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agent.nl_patch import parse_nl_patches
from app.booking.amend import amend_booking_record
from app.config import (
    AMEND_DEBUG_DUMP,
    BOOKING_FIELD_KEYS,
    DEBUG_DIR,
    LLM_TEXT_MODEL,
    OPENAI_TEMPERATURE,
    has_llm_key,
    make_openai_client,
    parse_backend,
)

logger = logging.getLogger("fj.amend_llm")

AMEND_TOOL_NAME = "amend_booking_record"

_AMEND_TOOL = {
    "type": "function",
    "function": {
        "name": AMEND_TOOL_NAME,
        "description": (
            "修正已提交订舱单的已录入字段。传入需要变更的 patches；"
            "若要将毛重单位在 KGS/TON 间换算，请设 convert_weight=true。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patches": {
                    "type": "object",
                    "description": (
                        "只含要改的业务字段。"
                        f"允许 key：{', '.join(BOOKING_FIELD_KEYS)}"
                    ),
                },
                "convert_weight": {
                    "type": "boolean",
                    "description": "单位 KGS↔TON 时是否按比例换算毛重",
                },
            },
            "required": ["patches"],
        },
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_tool_args(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _patches_from_tool_args(args: dict[str, Any]) -> dict[str, Any] | None:
    patches = dict(args.get("patches") or {})
    if args.get("convert_weight"):
        patches["_convert_weight"] = True
    if not patches:
        patches = {
            k: v
            for k, v in args.items()
            if k in BOOKING_FIELD_KEYS or k == "_convert_weight"
        }
    return patches or None


def _llm_tool_patches(
    text: str, current: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """强制 tool_call 出 patches；返回 (patches|None, step_detail)。"""
    detail: dict[str, Any] = {
        "step": "llm_tool",
        "model": LLM_TEXT_MODEL,
        "ok": False,
    }
    cur = json.dumps(current or {}, ensure_ascii=False)[:4000]
    keys = ", ".join(BOOKING_FIELD_KEYS)
    system = (
        "你是订舱单修正助手。单据已提交（Done），用户用自然语言要求修改已存盘字段。"
        f"你必须调用工具 {AMEND_TOOL_NAME}，在 patches 里填入要改的字段。\n"
        f"允许字段：{keys}\n"
        "规则：只传需要改的字段；数值用 JSON number；"
        "毛重单位 KGS↔TON 且需换算时 convert_weight=true。"
    )
    user = f"当前已存盘字段：\n{cur}\n\n用户指令：\n{text.strip()}"
    client = make_openai_client()
    base: dict[str, Any] = {
        "model": LLM_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "tools": [_AMEND_TOOL],
        "temperature": min(OPENAI_TEMPERATURE, 0.2),
    }
    extra = {"thinking": {"type": "disabled"}}

    try:
        resp = client.chat.completions.create(
            **base,
            tool_choice={
                "type": "function",
                "function": {"name": AMEND_TOOL_NAME},
            },
            extra_body=extra,
        )
        detail["tool_choice"] = "forced"
    except Exception as exc1:
        detail["forced_error"] = f"{type(exc1).__name__}: {exc1}"
        try:
            resp = client.chat.completions.create(
                **base, tool_choice="auto", extra_body=extra
            )
            detail["tool_choice"] = "auto"
        except Exception as exc2:
            detail["auto_error"] = f"{type(exc2).__name__}: {exc2}"
            logger.exception("amend LLM tools unavailable")
            return None, detail

    msg = resp.choices[0].message if resp.choices else None
    if not msg:
        detail["error"] = "empty_message"
        return None, detail

    tool_calls = getattr(msg, "tool_calls", None) or []
    detail["tool_call_count"] = len(tool_calls)
    content = (getattr(msg, "content", None) or "").strip()
    if content:
        detail["content_preview"] = content[:300]

    for tc in tool_calls:
        fn = getattr(tc, "function", None)
        name = getattr(fn, "name", None) if fn else None
        raw_args = getattr(fn, "arguments", None) if fn else None
        detail["tool_name"] = name
        detail["raw_arguments"] = (
            raw_args
            if isinstance(raw_args, str)
            else json.dumps(raw_args, ensure_ascii=False)
        )[:800]
        if name != AMEND_TOOL_NAME:
            continue
        args = _parse_tool_args(raw_args)
        patches = _patches_from_tool_args(args)
        if patches:
            detail["ok"] = True
            detail["patches"] = patches
            logger.info("amend tool_call patches=%s", list(patches.keys()))
            return patches, detail

    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    if content.startswith("{"):
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            detail["error"] = "content_not_json"
            return None, detail
        if isinstance(data, dict):
            patches = _patches_from_tool_args(data) or (
                data if any(k in BOOKING_FIELD_KEYS for k in data) else None
            )
            if patches:
                detail["ok"] = True
                detail["from_content_json"] = True
                detail["patches"] = patches
                return patches, detail
    detail["error"] = detail.get("error") or "no_usable_tool_args"
    return None, detail


def _summarize_patches(patches: dict[str, Any]) -> str:
    parts: list[str] = []
    for k, v in patches.items():
        if k.startswith("_"):
            continue
        parts.append(f"{k}={v!r}")
    if patches.get("_convert_weight"):
        parts.append("换算毛重")
    return "、".join(parts) if parts else ""


def _dump_amend_trace(trace: dict[str, Any]) -> str | None:
    if not AMEND_DEBUG_DUMP:
        return None
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = DEBUG_DIR / f"amend_{stamp}_{uuid.uuid4().hex[:8]}.json"
    path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("AMEND_DEBUG_DUMP → %s", path)
    return str(path)


def run_done_amend_from_text(
    session_id: str,
    text: str,
    *,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """NL → tool call / JSON 解析 → amend_booking_record。"""
    t = (text or "").strip()
    steps: list[dict[str, Any]] = []
    trace: dict[str, Any] = {
        "at": _now(),
        "session_id": session_id,
        "user_text": t,
        "text_model": LLM_TEXT_MODEL,
        "steps": steps,
    }

    empty = {
        "ok": False,
        "written": False,
        "changed_fields": [],
        "error_fields": [],
        "validated_data": current,
        "validation_report": None,
        "record": None,
        "understood": None,
    }

    if not t:
        empty["message"] = "请输入修正指令"
        steps.append({"step": "input", "ok": False, "error": "empty"})
        empty["amend_trace"] = trace
        _dump_amend_trace(trace)
        return empty

    patches: dict[str, Any] | None = None
    source = ""
    use_llm = has_llm_key() and parse_backend() != "fixture"
    steps.append({"step": "config", "use_llm": use_llm, "model": LLM_TEXT_MODEL})

    if use_llm:
        try:
            patches, tool_detail = _llm_tool_patches(t, current or {})
            steps.append(tool_detail)
            if patches:
                source = "tool"
        except Exception as exc:
            logger.exception("amend tool LLM error")
            steps.append(
                {
                    "step": "llm_tool",
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            patches = None

    if not patches:
        try:
            patches = parse_nl_patches(t, current=current)
            steps.append(
                {
                    "step": "nl_json",
                    "ok": bool(patches),
                    "patches": patches,
                    "model": LLM_TEXT_MODEL if use_llm else None,
                }
            )
            if patches:
                source = "nl_json"
        except Exception as exc:
            logger.exception("nl_json fallback failed")
            steps.append(
                {
                    "step": "nl_json",
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            patches = None

    if not patches:
        empty["message"] = (
            "未能识别修正内容。可试：把毛重单位从 KGS 换成 TON / 船名改成 XXX / 航次改成 V001"
        )
        steps.append({"step": "understand", "ok": False})
        dump = _dump_amend_trace(trace)
        if dump:
            empty["message"] += f"（轨迹已写 {dump}）"
        empty["amend_trace"] = trace
        return empty

    summary = _summarize_patches(patches)
    logger.info("amend understood via=%s %s", source, summary)
    steps.append(
        {"step": "understand", "ok": True, "source": source, "summary": summary}
    )

    result = amend_booking_record(session_id, patches, actor="llm")
    report = result.get("validation_report") or {}
    steps.append(
        {
            "step": "amend_write",
            "ok": bool(result.get("ok")),
            "written": bool(result.get("written")),
            "overall": report.get("overall") if isinstance(report, dict) else None,
            "changed_fields": result.get("changed_fields"),
            "error_fields": result.get("error_fields"),
        }
    )
    result["understood"] = {
        k: v for k, v in patches.items() if not str(k).startswith("_")
    }
    result["understand_source"] = source
    base_msg = result.get("message") or ""
    if summary:
        result["message"] = f"识别：{summary}。{base_msg}"

    dump = _dump_amend_trace(trace)
    trace["dump_path"] = dump
    result["amend_trace"] = trace
    return result
