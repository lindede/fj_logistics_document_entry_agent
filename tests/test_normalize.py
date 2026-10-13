from app.parse.normalize import normalize_extracted_text, normalize_text
from app.parse.schema_fill import fill_schema


def test_normalize_text_nfkc_and_space():
    # 全角数字/字母 → 半角；多空格折叠
    assert normalize_text("ＡＢＣ　１２３") == "ABC 123"
    assert normalize_text("  foo\n\tbar  ") == "foo bar"
    assert normalize_text("QINGDAO–CNTAO") == "QINGDAO-CNTAO"
    assert normalize_text("INT\u2019L") == "INT'L"


def test_normalize_extracted_text_fields():
    out = normalize_extracted_text(
        {
            "shipper": "  Acme　Co.  ",
            "packages_qty": "１６０",
            "containers": [{"type": "４０ＨＱ", "qty": "１"}],
            "gross_weight": 25600,
        }
    )
    assert out["shipper"] == "Acme Co."
    assert out["packages_qty"] == "160"
    assert out["containers"][0]["type"] == "40HQ"
    assert out["containers"][0]["qty"] == "1"
    assert out["gross_weight"] == 25600


def test_fill_schema_runs_normalize_then_coerce():
    out = fill_schema({"packages_qty": "１６０", "shipper": "Ａ\u00a0Ｂ"})
    assert out["packages_qty"] == 160
    assert out["shipper"] == "A B"
