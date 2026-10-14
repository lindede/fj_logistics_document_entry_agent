"""Done 态修正：改已存盘 BookingRecord，先验后写。"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import BOOKING_FIELD_KEYS, STORE_DIR
from app.models import BookingRecord
from app.parse.schema_fill import fill_schema
from app.validate import validate_booking

logger = logging.getLogger("fj.amend")

_CONTROL_KEYS = {"_convert_weight"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_patches(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (raw or {}).items():
        if k in _CONTROL_KEYS:
            if k == "_convert_weight":
                out[k] = bool(v)
            continue
        if k not in BOOKING_FIELD_KEYS:
            continue
        out[k] = v
    if out.get("_convert_weight") and "weight_unit" not in out:
        out.pop("_convert_weight", None)
    return out


def _convert_weight_unit(data: dict[str, Any], new_unit: str) -> dict[str, Any]:
    out = dict(data)
    old = str(out.get("weight_unit") or "").upper()
    new_u = new_unit.upper()
    if new_u == "MT":
        new_u = "TON"
    if old == "KG":
        old = "KGS"
    gw = out.get("gross_weight")
    if gw is not None and old and new_u and old != new_u:
        try:
            val = float(gw)
            if old == "KGS" and new_u == "TON":
                val = val / 1000.0
            elif old == "TON" and new_u == "KGS":
                val = val * 1000.0
            out["gross_weight"] = round(val, 6) if new_u == "TON" else round(val, 3)
        except (TypeError, ValueError):
            pass
    out["weight_unit"] = new_u
    return out


def store_path(session_id: str, *, root: Path | None = None) -> Path:
    base = root or STORE_DIR
    return base / f"{session_id}.json"


def load_stored_record(
    session_id: str, *, root: Path | None = None
) -> BookingRecord | None:
    path = store_path(session_id, root=root)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("load store failed: %s", path)
        return None
    if not isinstance(raw, dict):
        return None
    # 提交时额外字段忽略
    raw.pop("submitted_at", None)
    raw.pop("submitted_by", None)
    try:
        return BookingRecord.model_validate(raw)
    except Exception:
        logger.exception("invalid BookingRecord in %s", path)
        return None


def _apply_patches(
    data: dict[str, Any], patches: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    out = fill_schema(deepcopy(data or {}))
    clean = _sanitize_patches(dict(patches or {}))
    convert = bool(clean.pop("_convert_weight", False))
    changed: list[str] = []
    if convert and "weight_unit" in clean:
        out = _convert_weight_unit(out, str(clean["weight_unit"]))
        clean = {**clean, "gross_weight": out.get("gross_weight")}
    for k, v in clean.items():
        if k not in BOOKING_FIELD_KEYS:
            continue
        if out.get(k) != v:
            changed.append(k)
        out[k] = v
    # 换算可能改了毛重但 patches 未显式列出
    if convert and "gross_weight" in clean and "gross_weight" not in changed:
        if data.get("gross_weight") != out.get("gross_weight"):
            changed.append("gross_weight")
    if convert and "weight_unit" in clean and "weight_unit" not in changed:
        changed.append("weight_unit")
    # 去重保序
    seen: set[str] = set()
    ordered: list[str] = []
    for k in changed:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    return out, ordered


def amend_booking_record(
    session_id: str,
    patches: dict[str, Any],
    *,
    root: Path | None = None,
    actor: str = "llm",
) -> dict[str, Any]:
    """合并 patches → 校验 → FAIL 不落盘；PASS/WARN 写回 store。

    返回供 UI / Agent 使用的结果字典（FAIL 时仍带预览数据与报告）。
    """
    sid = (session_id or "").strip()
    if not sid:
        return {
            "ok": False,
            "written": False,
            "changed_fields": [],
            "error_fields": [],
            "message": "缺少 session_id",
            "validated_data": None,
            "validation_report": None,
            "record": None,
        }

    record = load_stored_record(sid, root=root)
    if record is None:
        return {
            "ok": False,
            "written": False,
            "changed_fields": [],
            "error_fields": [],
            "message": "未找到已提交存盘记录，无法修正",
            "validated_data": None,
            "validation_report": None,
            "record": None,
        }

    clean = _sanitize_patches(dict(patches or {}))
    if not clean:
        return {
            "ok": False,
            "written": False,
            "changed_fields": [],
            "error_fields": [],
            "message": "没有可应用的字段修改",
            "validated_data": record.validated_data,
            "validation_report": (
                record.validation_report.model_dump()
                if record.validation_report
                else None
            ),
            "record": record.model_dump(),
        }

    base = dict(record.validated_data or {})
    merged, changed = _apply_patches(base, clean)
    conf: dict[str, float] = {}
    if record.validation_report:
        conf = dict(record.validation_report.field_confidence or {})
    for k in changed:
        conf[k] = 0.95

    validated, report = validate_booking(merged, field_confidence=conf)
    report_dump = report.model_dump()
    error_fields = sorted(
        {
            i.field
            for i in report.issues
            if i.level in {"FAIL", "WARN"} and i.field
        }
        | set(report.low_confidence_fields or [])
    )

    # FAIL 不落盘；PASS/WARN 可写（WARN 仍标出问题字段供 UI 高亮）
    if report.overall == "FAIL":
        return {
            "ok": False,
            "written": False,
            "changed_fields": changed,
            "error_fields": error_fields,
            "message": "校验未通过（FAIL），未写入存盘；请继续用指令修正",
            "validated_data": validated,
            "validation_report": report_dump,
            "record": record.model_dump(),
        }

    hist = list(record.history or [])
    hist.append(
        {
            "at": _now(),
            "action": "amend",
            "actor": actor,
            "detail": {"patches": {k: validated.get(k) for k in changed}},
        }
    )
    msg = (
        "已按指令修正并校验通过"
        if report.overall == "PASS"
        else "已修正并存盘（仍有警告，请核对高亮字段）"
    )
    updated = record.model_copy(
        update={
            "validated_data": validated,
            "normalized_data": validated,
            "validation_report": report,
            "history": hist,
            "message": msg,
            "status": "Done",
        }
    )
    path = store_path(sid, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = updated.model_dump()
    # 保留原提交元数据（若文件里有）
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(prev, dict):
            if "submitted_at" in prev:
                payload["submitted_at"] = prev["submitted_at"]
            if "submitted_by" in prev:
                payload["submitted_by"] = prev["submitted_by"]
    except (OSError, json.JSONDecodeError):
        pass
    payload["amended_at"] = _now()
    payload["amended_by"] = actor
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    detail = "、".join(changed) if changed else ""
    return {
        "ok": True,
        "written": True,
        "changed_fields": changed,
        "error_fields": error_fields if report.overall == "WARN" else [],
        "message": (f"{msg}：{detail}" if detail else msg),
        "validated_data": validated,
        "validation_report": report_dump,
        "record": updated.model_dump(),
    }
