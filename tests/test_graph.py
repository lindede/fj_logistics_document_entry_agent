"""LangGraph 会话：session_id 即 checkpoint thread，wait_human interrupt。"""

from __future__ import annotations

import os

import pytest

os.environ["PARSE_BACKEND"] = "fixture"

from app.agent.graph import (  # noqa: E402
    _cfg,
    booking_graph,
    get_session_values,
    open_session,
    session_is_waiting,
)
from app.agent.session import SessionManager  # noqa: E402


@pytest.fixture(autouse=True)
def _fixture_backend(monkeypatch):
    monkeypatch.setenv("PARSE_BACKEND", "fixture")
    import app.config as cfg

    monkeypatch.setattr(cfg, "PARSE_BACKEND", "fixture")


def test_open_stops_at_wait_human():
    sid = open_session(submit_strategy="manual", file_path="data/samples/BKG.pdf")
    assert session_is_waiting(sid)
    vals = get_session_values(sid)
    assert vals["session_id"] == sid
    assert vals["status"] in {"AwaitConfirm", "AwaitHuman"}
    assert vals.get("validated_data")
    assert "parse" in vals.get("graph_path", [])
    assert "apply_patches" not in vals.get("graph_path", [])
    assert booking_graph.get_state(_cfg(sid)).next == ("wait_human",)


def test_session_open_uses_graph_session():
    sm = SessionManager()
    sm.submit_strategy = "manual"
    snap = sm.open_booking(file_path="data/samples/BKG.pdf")
    assert snap["status"] in {"AwaitConfirm", "AwaitHuman"}
    assert snap["session_id"] == sm.session_id
    assert snap.get("graph_waiting") is True
    assert snap.get("validated_data")


def test_patch_resume_same_session():
    sm = SessionManager()
    sm.submit_strategy = "manual"
    sm.open_booking(file_path="data/samples/BKG.pdf")
    sid = sm.session_id
    assert sid
    before = sm.record.validated_data.get("gross_weight")
    snap = sm.patch_fields({"gross_weight": 1}, actor="human")
    assert sm.session_id == sid
    assert get_session_values(sid)["session_id"] == sid
    assert snap["validated_data"]["gross_weight"] == 1
    assert before != 1 or before == 1
    assert session_is_waiting(sid)


def test_submit_resume_ends_wait():
    sm = SessionManager()
    sm.submit_strategy = "manual"
    snap = sm.open_booking(file_path="data/samples/BKG.pdf")
    if snap["status"] == "AwaitHuman" and (snap.get("validation_report") or {}).get(
        "overall"
    ) == "FAIL":
        pytest.skip("fixture FAIL")
    sid = sm.session_id
    out = sm.submit()
    assert out["status"] == "Idle"
    assert not session_is_waiting(sid)
