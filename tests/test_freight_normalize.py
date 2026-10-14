"""freight 单据写法 → P/C/E 规整。"""

from app.parse.extract import _normalize_freight, _normalize_llm_fields


def test_normalize_freight_aliases():
    assert _normalize_freight("P") == "P"
    assert _normalize_freight("Prepaid") == "P"
    assert _normalize_freight("预付金额 Prepaid") == "P"
    assert _normalize_freight("FREIGHT PREPAID") == "P"
    assert _normalize_freight("Collect") == "C"
    assert _normalize_freight("到付") == "C"
    assert _normalize_freight("Payable Elsewhere") == "E"
    assert _normalize_freight("约定") == "E"
    assert _normalize_freight("") is None
    assert _normalize_freight(None) is None
    assert _normalize_freight("unknown") is None


def test_normalize_llm_fields_maps_freight():
    out = _normalize_llm_fields({"freight": "预付金额 Prepaid"})
    assert out["freight"] == "P"


def test_fixture_parse_separates_raw_and_normalized(monkeypatch):
    monkeypatch.setenv("PARSE_BACKEND", "fixture")
    from app.parse.extract import parse_pdf_bytes

    parsed = parse_pdf_bytes(open("data/samples/BKG.pdf", "rb").read())
    assert "normalized_data" in parsed
    assert parsed["raw_extracted_data"]["freight"] == "P"
    assert parsed["normalized_data"]["freight"] == "P"
    assert parsed.get("llm_analysis") is None
