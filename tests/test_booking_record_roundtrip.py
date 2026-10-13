"""BookingRecord 存取往返：validated_data 不得丢失或变形。"""

from __future__ import annotations

import copy
import json

from app.models import BookingRecord, ValidationReport
from app.validate.schema_check import check_schema
from tests.test_validate import _base


def _sample_validated() -> dict:
    """含嵌套、null、空航次、数值 —— 易在序列化中丢损的形态。"""
    return _base(
        voyage="",
        containers=[{"type": "40HQ", "qty": 2}, {"type": "20GP", "qty": 1}],
        packages_qty=160,
        gross_weight=2150.5,
        measurement=12.3,
        hs_code=None,
        marks=None,
        freight="P",
    )


def test_validated_data_survives_model_dump_and_validate():
    original = _sample_validated()
    assert check_schema(original) == []

    record = BookingRecord(
        session_id="00000000-0000-4000-8000-000000000001",
        status="AwaitConfirm",
        message="roundtrip",
        filename="sample.pdf",
        raw_extracted_data=copy.deepcopy(original),
        validated_data=copy.deepcopy(original),
        validation_report=ValidationReport(
            overall="PASS",
            issues=[],
            field_confidence={"vessel": 0.9},
            suggested_action="confirm",
        ),
        meta={"fields": {"vessel": {"source": "llm"}}},
        history=[{"at": "2026-01-01T00:00:00+00:00", "action": "parse_validate", "actor": "llm", "detail": {}}],
    )

    # Record → JSON 文本 → dict → Record（模拟落盘再读回）
    as_json = json.dumps(record.model_dump(), ensure_ascii=False)
    loaded = BookingRecord.model_validate(json.loads(as_json))

    assert loaded.validated_data == original
    assert loaded.raw_extracted_data == original
    assert check_schema(loaded.validated_data) == []
    assert loaded.validation_report is not None
    assert loaded.validation_report.overall == "PASS"
    assert loaded.meta["fields"]["vessel"]["source"] == "llm"
    assert loaded.history[0]["action"] == "parse_validate"


def test_validated_data_json_text_roundtrip_byte_stable_keys():
    """经 JSON 字符串往返后，关键字段类型与取值不变。"""
    original = _sample_validated()
    record = BookingRecord(
        session_id="sid",
        status="AwaitConfirm",
        validated_data=copy.deepcopy(original),
    )
    dumped = json.loads(json.dumps(record.model_dump()["validated_data"]))

    assert dumped["packages_qty"] == 160
    assert isinstance(dumped["packages_qty"], int)
    assert dumped["gross_weight"] == 2150.5
    assert dumped["voyage"] == ""
    assert dumped["hs_code"] is None
    assert dumped["freight"] == "P"
    assert dumped["containers"] == [
        {"type": "40HQ", "qty": 2},
        {"type": "20GP", "qty": 1},
    ]
    assert check_schema(dumped) == []
