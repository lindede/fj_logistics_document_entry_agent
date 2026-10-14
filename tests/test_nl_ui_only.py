"""Await 态不再走 ui_patches；文字修正仅 Done。"""

from __future__ import annotations

import os

import pytest

os.environ["PARSE_BACKEND"] = "fixture"

from app.agent.session import SessionManager  # noqa: E402


@pytest.fixture(autouse=True)
def _fixture_backend(monkeypatch):
    monkeypatch.setenv("PARSE_BACKEND", "fixture")
    import app.config as cfg

    monkeypatch.setattr(cfg, "PARSE_BACKEND", "fixture")


def test_chat_nl_in_await_does_not_apply_ui_only():
    sm = SessionManager()
    sm.submit_strategy = "manual"
    sm.open_booking(file_path="data/samples/BKG.pdf")
    before = dict(sm.record.validated_data or {})
    out = sm.handle(action="chat", text="毛重改成吨")
    assert out.get("apply_ui_only") is not True
    assert "ui_patches" not in out
    after = sm.record.validated_data or {}
    assert after.get("gross_weight") == before.get("gross_weight")
    assert after.get("weight_unit") == before.get("weight_unit")
