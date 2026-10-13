"""VAL-07：人工修正回流。pending 存原 PDF；仅 human 改过再提交才晋升为 feedback case。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import FEEDBACK_DIR
from app.models import BookingRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pending_dir(session_id: str, *, root: Path | None = None) -> Path:
    base = root or FEEDBACK_DIR
    return base / "_pending" / session_id


def case_dir(session_id: str, *, root: Path | None = None) -> Path:
    base = root or FEEDBACK_DIR
    return base / session_id


def save_pending_source(
    session_id: str,
    pdf_bytes: bytes,
    filename: str | None = None,
    *,
    root: Path | None = None,
) -> Path:
    """开票时写入 staging：source.pdf。"""
    d = pending_dir(session_id, root=root)
    d.mkdir(parents=True, exist_ok=True)
    pdf_path = d / "source.pdf"
    pdf_path.write_bytes(pdf_bytes)
    meta = {
        "filename": filename or "source.pdf",
        "saved_at": _now(),
        "bytes": len(pdf_bytes),
    }
    (d / "source_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return pdf_path


def discard_pending(session_id: str, *, root: Path | None = None) -> None:
    d = pending_dir(session_id, root=root)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def human_fields(meta: dict[str, Any] | None) -> list[str]:
    fields = (meta or {}).get("fields") or {}
    return sorted(
        k for k, info in fields.items() if isinstance(info, dict) and info.get("source") == "human"
    )


def is_human_touched(meta: dict[str, Any] | None) -> bool:
    if not meta:
        return False
    if meta.get("human_touched"):
        return True
    return bool(human_fields(meta))


def promote_or_discard(
    record: BookingRecord,
    *,
    actor: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """
    提交时：有人工修改 → pending 晋升为 feedback/<sid>/（source.pdf + gold.json）；
    否则丢弃 pending。返回动作摘要。
    """
    sid = record.session_id
    touched = is_human_touched(record.meta)
    pending = pending_dir(sid, root=root)

    if not touched:
        discard_pending(sid, root=root)
        return {"feedback": "skipped", "reason": "no_human_edit", "session_id": sid}

    out = case_dir(sid, root=root)
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)

    src_pdf = pending / "source.pdf"
    if src_pdf.exists():
        shutil.copy2(src_pdf, out / "source.pdf")
        src_meta = pending / "source_meta.json"
        if src_meta.exists():
            shutil.copy2(src_meta, out / "source_meta.json")
    else:
        # 无 pending PDF 时仍写 gold，并注明缺失（便于排查）
        (out / "source_missing.txt").write_text(
            "source.pdf was not saved at open\n", encoding="utf-8"
        )

    hf = human_fields(record.meta)
    gold = {
        "validated_data": record.validated_data,
        "session_id": sid,
        "filename": record.filename,
        "submitted_at": _now(),
        "submitted_by": actor,
        "human_fields": hf,
        "meta": record.meta or {},
        "history_tail": list(record.history or [])[-10:],
    }
    (out / "gold.json").write_text(
        json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    discard_pending(sid, root=root)
    return {
        "feedback": "promoted",
        "session_id": sid,
        "path": str(out),
        "human_fields": hf,
    }
