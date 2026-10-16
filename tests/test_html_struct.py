"""html_struct：规则抽取，不调模型。"""

from pathlib import Path

from app.parse.extract import _normalize_llm_fields, parse_pdf_bytes
from app.parse.html_struct import extract_html_struct, split_number_unit

_BKG = Path("data/samples/BKG.pdf")


def test_split_keeps_stray_letters():
    number, unit = split_number_unit("2560OKGS", "KGS")
    assert number == "2560OKGS"
    assert "O" in number
    assert number not in (2560, 25600, "2560", "25600")
    assert unit == "KGS"


def test_dirty_weight_stays_visible_as_failure():
    from app.validate.rules import br_02_ranges
    from app.validate.schema_check import check_schema

    number, unit = split_number_unit("2560OKGS", "KGS")
    data = _normalize_llm_fields(
        {
            "gross_weight": number,
            "weight_unit": unit,
            "containers": [{"type": "40HQ", "qty": 1}],
        }
    )
    assert data["gross_weight"] == "2560OKGS"
    messages = [issue.message for issue in br_02_ranges(data) + check_schema(data)]
    assert any("2560OKGS" in message for message in messages)


def test_split_exact_number_and_known_unit():
    assert split_number_unit("25600KGS", None) == (25600, "KGS")
    assert split_number_unit("160CTNS", None) == (160, "CTNS")


def test_bare_number_uses_header_unit_only():
    assert split_number_unit("32.03", "CBM") == (32.03, "CBM")
    assert split_number_unit("32.03", None) == (32.03, None)


def test_bkg_html_struct_matches_fields():
    raw = extract_html_struct(_BKG.read_bytes())
    assert raw["gross_weight"] == 25600
    assert "可充电锂离子电芯" in raw["goods_desc"]
    assert "Rechargeable Li-ion Cell" in raw["goods_desc"]
    assert "预付" in raw["freight"]
    assert "Prepaid" in raw["freight"]

    data = _normalize_llm_fields(raw)
    assert data["shipper"] == "Guangzhou Great PowerEnergy (Qingdao) Co., Ltd."
    assert data["consignee"] == "GREAT POWER NEW ENERGY CO., LTD"
    assert data["notify_party"] == "TENV INNOVATIONS PRIVATE LIMITED"
    assert data["vessel"] == "MSC"
    assert data["voyage"] == ""
    assert data["port_of_loading"] == "QINGDAO"
    assert data["port_of_discharge"] == "NHAVA SHEVA"
    assert data["containers"] == [{"type": "40HQ", "qty": 1}]
    assert data["packages_qty"] == 160
    assert data["packages_unit"] == "CTNS"
    assert data["goods_desc"] == "Rechargeable Li-ion Cell 可充电锂离子电芯"
    assert data["gross_weight"] == 25600
    assert data["weight_unit"] == "KGS"
    assert data["measurement"] == 32.03
    assert data["measurement_unit"] == "CBM"
    assert data["marks"] is None
    assert data["hs_code"] is None
    assert data["freight"] == "P"


def test_parse_pdf_bytes_html_struct_skips_llm(monkeypatch):
    monkeypatch.setenv("PARSE_BACKEND", "llm")
    monkeypatch.setenv("LLM_INPUT_MODE", "html_struct")
    monkeypatch.setattr("app.parse.extract.has_llm_key", lambda: False)
    out = parse_pdf_bytes(_BKG.read_bytes())
    assert out["backend"] == "llm:html_struct"
    assert out["llm_analysis"] is None
    assert out["normalized_data"]["notify_party"] == "TENV INNOVATIONS PRIVATE LIMITED"
    assert out["normalized_data"]["measurement_unit"] == "CBM"
