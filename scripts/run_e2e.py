#!/usr/bin/env python3
"""端到端验收：UC-01 / UC-02 / UC-04 / ADV-01 片段。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.session import SessionManager  # noqa: E402


def main() -> int:
    sm = SessionManager()
    sm.submit_strategy = "manual"

    # UC-01 开票 → 待确认 → 提交
    s = sm.open_booking(file_path="data/samples/BKG.pdf")
    assert s["status"] in {"AwaitConfirm", "AwaitHuman"}, s
    assert s["raw_extracted_data"] and s["validated_data"] and s["validation_report"]
    assert s["meta"].get("fields")
    assert any(h["action"] == "parse_validate" for h in s["history"])
    if s["validation_report"]["overall"] != "FAIL":
        s = sm.submit()
        assert s["status"] == "Idle", s

    # UC-02 FAIL 再修正
    sm = SessionManager()
    s = sm.open_booking(file_path="data/samples/BKG_fail_same_ports.pdf")
    assert s["status"] == "AwaitHuman", s
    s = sm.patch_fields(
        {"port_of_discharge": "NHAVA SHEVA -- INNSA"}, actor="human"
    )
    assert s["validation_report"]["overall"] != "FAIL" or s["status"] in {
        "AwaitConfirm",
        "AwaitHuman",
    }
    # 修正后应不再有 BR-01
    rules = {i["rule"] for i in s["validation_report"]["issues"]}
    assert "BR-01" not in rules, rules

    # UC-04 作废
    s = sm.void()
    assert s["status"] == "Idle"

    # ADV-01 自然语言改单位
    sm = SessionManager()
    sm.open_booking(file_path="data/samples/BKG.pdf")
    s = sm.handle(text="把毛重单位从 KGS 换成 TON")
    assert s["validated_data"]["weight_unit"] == "TON"
    assert float(s["validated_data"]["gross_weight"]) == 25.6

    # 换票冲突
    sm = SessionManager()
    sm.open_booking(file_path="data/samples/BKG.pdf")
    s = sm.handle(file_path="data/samples/BKG.pdf")
    assert s.get("replace_pending") or "换票" in (s.get("message") or "")

    print("E2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
