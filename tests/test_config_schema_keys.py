from app.config import (
    BOOKING_DATA_SCHEMA_PATH,
    BOOKING_FIELD_KEYS,
    OPTIONAL_NULL_KEYS,
    REQUIRED_KEYS,
)


def test_keys_derived_from_json_schema():
    assert BOOKING_DATA_SCHEMA_PATH.exists()
    assert "shipper" in BOOKING_FIELD_KEYS
    assert "freight" in BOOKING_FIELD_KEYS
    assert OPTIONAL_NULL_KEYS == ["hs_code", "marks", "freight"]
    assert "voyage" not in REQUIRED_KEYS
    assert "shipper" in REQUIRED_KEYS
    assert "hs_code" not in REQUIRED_KEYS
    # 顺序与 schema properties 一致
    assert BOOKING_FIELD_KEYS[0] == "shipper"
    assert BOOKING_FIELD_KEYS[-1] == "freight"
