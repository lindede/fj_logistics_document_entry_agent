"""VAL-07：仅人工改过再提交才晋升 feedback case。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.session import SessionManager
from app.booking.feedback import (
    case_dir,
    discard_pending,
    pending_dir,
    promote_or_discard,
    save_pending_source,
)
from app.models import BookingRecord, ValidationReport


@pytest.fixture
def fb_root(tmp_path, monkeypatch):
    root = tmp_path / "feedback"
    root.mkdir()
    monkeypatch.setattr("app.booking.feedback.FEEDBACK_DIR", root)
    monkeypatch.setattr("app.config.FEEDBACK_DIR", root)
    return root


def test_pending_source_saved_on_open(fb_root):
    sm = SessionManager()
    sm.submit_strategy = "manual"
    snap = sm.open_booking(file_path="data/samples/BKG.pdf")
    sid = snap["session_id"]
    pdf = pending_dir(sid, root=fb_root) / "source.pdf"
    assert pdf.exists()
    assert pdf.read_bytes()[:4] == b"%PDF"


def test_submit_without_human_discards_pending(fb_root):
    sm = SessionManager()
    sm.submit_strategy = "manual"
    snap = sm.open_booking(file_path="data/samples/BKG.pdf")
    sid = snap["session_id"]
    assert (pending_dir(sid, root=fb_root) / "source.pdf").exists()

    # 校验可能是 WARN/PASS；FAIL 则无法 submit——fixture 样例通常可确认
    if snap["status"] == "AwaitHuman" and snap.get("validation_report", {}).get("overall") == "FAIL":
        pytest.skip("fixture sample failed hard; cannot submit")
    out = sm.submit()
    assert out["status"] == "Done"
    assert not pending_dir(sid, root=fb_root).exists()
    assert not case_dir(sid, root=fb_root).exists()


def test_submit_after_human_patch_promotes(fb_root):
    sm = SessionManager()
    sm.submit_strategy = "manual"
    snap = sm.open_booking(file_path="data/samples/BKG.pdf")
    sid = snap["session_id"]
    sm.patch_fields({"voyage": "TESTVOY"}, actor="human")
    assert sm.record and sm.record.meta.get("human_touched")

    # 若仍 FAIL，改掉会拦提交的字段——样例一般非 FAIL
    report = sm.record.validation_report
    if report and report.overall == "FAIL":
        pytest.skip("still FAIL after patch")
    sm.submit()
    case = case_dir(sid, root=fb_root)
    assert (case / "source.pdf").exists()
    gold = json.loads((case / "gold.json").read_text(encoding="utf-8"))
    assert gold["validated_data"]["voyage"] == "TESTVOY"
    assert "voyage" in gold["human_fields"]
    assert not pending_dir(sid, root=fb_root).exists()


def test_void_discards_pending(fb_root):
    sm = SessionManager()
    sm.submit_strategy = "manual"
    snap = sm.open_booking(file_path="data/samples/BKG.pdf")
    sid = snap["session_id"]
    sm.void()
    assert not pending_dir(sid, root=fb_root).exists()


def test_promote_or_discard_unit(fb_root):
    sid = "case-human"
    save_pending_source(sid, b"%PDF-1.4 fake", "t.pdf", root=fb_root)
    record = BookingRecord(
        session_id=sid,
        status="AwaitConfirm",
        validated_data={"vessel": "MSC", "voyage": "V1"},
        validation_report=ValidationReport(overall="PASS"),
        meta={"human_touched": True, "fields": {"voyage": {"source": "human"}}},
        history=[],
    )
    info = promote_or_discard(record, actor="human", root=fb_root)
    assert info["feedback"] == "promoted"
    assert (case_dir(sid, root=fb_root) / "gold.json").exists()

    sid2 = "case-llm"
    save_pending_source(sid2, b"%PDF-1.4 x", root=fb_root)
    r2 = BookingRecord(
        session_id=sid2,
        status="AwaitConfirm",
        validated_data={"vessel": "MSC"},
        meta={"fields": {"vessel": {"source": "llm"}}},
    )
    info2 = promote_or_discard(r2, actor="human", root=fb_root)
    assert info2["feedback"] == "skipped"
    assert not case_dir(sid2, root=fb_root).exists()
    discard_pending(sid2, root=fb_root)
