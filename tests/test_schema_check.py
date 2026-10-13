from app.validate import validate_booking
from app.validate.schema_check import check_schema
from tests.test_validate import _base


def test_schema_ok_on_base():
    assert check_schema(_base()) == []


def test_schema_rejects_non_int_packages():
    issues = check_schema(_base(packages_qty="约160"))
    assert issues
    assert any(i.rule == "STRUCT-SCHEMA" for i in issues)


def test_validate_booking_includes_schema():
    _, report = validate_booking(_base(gross_weight="heavy"))
    assert report.overall == "FAIL"
    assert any(i.rule == "STRUCT-SCHEMA" for i in report.issues)
