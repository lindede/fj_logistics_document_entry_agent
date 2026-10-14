"""文字指令只返回 ui_patches，不改 graph / 服务器 validated_data。"""

from __future__ import annotations

import os

import pytest

os.environ["PARSE_BACKEND"] = "fixture"

from app.agent.session import SessionManager  # noqa: E402


@pytest.fixture(autouse=True)
def _fixture_backend(monkeypatch):
    monkeypatch.setenv("PARSE_BACKEND", "fixture")
    import app.config as cfg
    import app.agent.nl_patch as nl

    monkeypatch.setattr(cfg, "PARSE_BACKEND", "fixture")
    monkeypatch.setattr(nl, "parse_backend", lambda: "fixture")


def test_chat_nl_does_not_mutate_server_fields(monkeypatch):
    sm = SessionManager()
    sm.submit_strategy = "manual"
    sm.open_booking(file_path="data/samples/BKG.pdf")
    before = dict(sm.record.validated_data or {})
    gw_before = before.get("gross_weight")

    monkeypatch.setattr(
        "app.agent.session.parse_nl_patches",
        lambda text, current=None: {
            "weight_unit": "TON",
            "_convert_weight": True,
        },
    )
    out = sm.handle(action="chat", text="毛重改成吨")
    assert out.get("apply_ui_only") is True
    assert out.get("ui_patches", {}).get("weight_unit") == "TON"
    assert "gross_weight" in out["ui_patches"]
    # 服务器侧未变
    after = sm.record.validated_data or {}
    assert after.get("gross_weight") == gw_before
    assert after.get("weight_unit") == before.get("weight_unit")
