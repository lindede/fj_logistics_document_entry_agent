"""Done 态 amend：先验后写 store。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["PARSE_BACKEND"] = "fixture"

from app.booking.amend import amend_booking_record, store_path  # noqa: E402
from app.models import BookingRecord, ValidationReport  # noqa: E402


def _seed_store(root: Path, sid: str, *, weight_unit: str = "KGS", gw: float = 1000.0):
    report = ValidationReport(
        overall="PASS",
        issues=[],
        field_confidence={"gross_weight": 0.9, "weight_unit": 0.9},
        suggested_action="await_confirm_or_auto_submit",
    )
    data = {
        "shipper": "A CO",
        "consignee": "B CO",
        "notify_party": "B CO",
        "vessel": "TEST VESSEL",
        "voyage": "V1",
        "port_of_loading": "SHANGHAI",
        "port_of_discharge": "SINGAPORE",
        "containers": [{"type": "40HQ", "qty": 1}],
        "packages_qty": 10,
        "packages_unit": "PKGS",
        "goods_desc": "GOODS",
        "gross_weight": gw,
        "weight_unit": weight_unit,
        "measurement": 1.0,
        "measurement_unit": "CBM",
        "hs_code": None,
        "marks": None,
        "freight": "P",
    }
    rec = BookingRecord(
        session_id=sid,
        status="Done",
        validated_data=data,
        normalized_data=data,
        validation_report=report,
        history=[],
        message="已提交",
    )
    path = store_path(sid, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = rec.model_dump()
    payload["submitted_at"] = "2026-01-01T00:00:00+00:00"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_amend_writes_only_on_pass(tmp_path):
    sid = "amend-ok"
    _seed_store(tmp_path, sid)
    out = amend_booking_record(
        sid,
        {"weight_unit": "TON", "_convert_weight": True},
        root=tmp_path,
        actor="test",
    )
    assert out["ok"] is True
    assert out["written"] is True
    assert "weight_unit" in out["changed_fields"]
    assert out["validated_data"]["weight_unit"] == "TON"
    assert out["validated_data"]["gross_weight"] == 1.0
    loaded = json.loads(store_path(sid, root=tmp_path).read_text(encoding="utf-8"))
    assert loaded["validated_data"]["weight_unit"] == "TON"
    assert loaded.get("amended_by") == "test"


def test_amend_rejects_fail_without_write(tmp_path):
    sid = "amend-fail"
    _seed_store(tmp_path, sid)
    before = store_path(sid, root=tmp_path).read_text(encoding="utf-8")
    out = amend_booking_record(
        sid,
        {"port_of_loading": "SINGAPORE", "port_of_discharge": "SINGAPORE"},
        root=tmp_path,
    )
    assert out["ok"] is False
    assert out["written"] is False
    assert out["validation_report"]["overall"] == "FAIL"
    assert store_path(sid, root=tmp_path).read_text(encoding="utf-8") == before
    assert "port_of_loading" in out["changed_fields"] or "port_of_discharge" in out[
        "changed_fields"
    ]


def test_session_done_chat_amends(monkeypatch, tmp_path):
    monkeypatch.setenv("PARSE_BACKEND", "fixture")
    import app.config as cfg
    import app.agent.graph as graph_mod
    from app.agent.session import SessionManager
    from app.booking import amend as amend_mod

    monkeypatch.setattr(cfg, "PARSE_BACKEND", "fixture")
    monkeypatch.setattr(cfg, "STORE_DIR", tmp_path)
    monkeypatch.setattr(graph_mod, "STORE_DIR", tmp_path)
    monkeypatch.setattr(amend_mod, "STORE_DIR", tmp_path)

    sm = SessionManager()
    sm.submit_strategy = "manual"
    sm.open_booking(file_path="data/samples/BKG.pdf")
    if sm.record.status == "AwaitHuman":
        # fixture 若 FAIL，强制提交到 Done
        sm.submit(force=True)
    else:
        sm.submit()
    assert sm.snapshot()["status"] == "Done"

    monkeypatch.setattr(
        "app.agent.amend_llm.parse_nl_patches",
        lambda text, current=None: {
            "weight_unit": "TON",
            "_convert_weight": True,
        },
    )
    monkeypatch.setattr(
        "app.agent.amend_llm.has_llm_key", lambda: False
    )

    out = sm.handle(action="chat", text="毛重单位换成 TON")
    assert out["status"] == "Done"
    assert out.get("amend_written") is True
    assert "weight_unit" in (out.get("highlight_fields") or [])
    assert (out.get("validated_data") or {}).get("weight_unit") == "TON"


def test_await_chat_nl_rejected(monkeypatch):
    monkeypatch.setenv("PARSE_BACKEND", "fixture")
    import app.config as cfg
    from app.agent.session import SessionManager

    monkeypatch.setattr(cfg, "PARSE_BACKEND", "fixture")
    sm = SessionManager()
    sm.submit_strategy = "manual"
    sm.open_booking(file_path="data/samples/BKG.pdf")
    assert sm.snapshot()["status"] in {"AwaitConfirm", "AwaitHuman"}
    out = sm.handle(action="chat", text="把船名改成 MSC")
    assert out.get("apply_ui_only") is not True
    assert "Done" in (out.get("message") or "") or "表单" in (out.get("message") or "")
