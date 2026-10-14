"""WARN/FAIL 时普通提交拒绝，强制提交可通过。"""

from __future__ import annotations

import os

os.environ["PARSE_BACKEND"] = "fixture"

from app.agent.session import SessionManager


def test_submit_blocks_fail_unless_force():
    sm = SessionManager()
    sm.submit_strategy = "manual"
    sm.open_booking(file_path="data/samples/BKG.pdf")
    sm.patch_fields(
        {
            "port_of_loading": "QINGDAO",
            "port_of_discharge": "QINGDAO",
        }
    )
    assert (sm.snapshot().get("validation_report") or {}).get("overall") == "FAIL"

    blocked = sm.submit(force=False)
    assert blocked.get("status") != "Idle"
    assert "FAIL" in (blocked.get("message") or "")

    forced = sm.submit(force=True)
    assert forced.get("status") == "Done"
    assert forced.get("validated_data")


def test_submit_blocks_warn_unless_force():
    sm = SessionManager()
    sm.submit_strategy = "manual"
    sm.open_booking(file_path="data/samples/BKG.pdf")
    assert sm.snapshot().get("status") in {"AwaitConfirm", "AwaitHuman"}

    orig = sm._values

    def warn_values():
        v = orig()
        report = dict(v.get("validation_report") or {})
        report["overall"] = "WARN"
        return {**v, "validation_report": report}

    sm._values = warn_values  # type: ignore[method-assign]

    blocked = sm.submit(force=False)
    assert blocked.get("status") != "Idle"
    assert "WARN" in (blocked.get("message") or "")

    forced = sm.submit(force=True)
    assert forced.get("status") == "Done"
