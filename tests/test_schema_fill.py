from app.parse.schema_fill import fill_schema


def test_coerce_numeric_strings():
    out = fill_schema(
        {
            "packages_qty": "160",
            "gross_weight": "25600.5",
            "measurement": "32.03",
            "containers": [{"type": "40HQ", "qty": "1"}],
        }
    )
    assert out["packages_qty"] == 160
    assert out["gross_weight"] == 25600.5
    assert out["measurement"] == 32.03
    assert out["containers"][0]["qty"] == 1


def test_do_not_force_non_numeric():
    out = fill_schema(
        {
            "packages_qty": "约160",
            "gross_weight": "N/A",
            "measurement": "",
            "containers": [{"type": "40HQ", "qty": "one"}],
        }
    )
    assert out["packages_qty"] == "约160"
    assert out["gross_weight"] == "N/A"
    assert out["measurement"] == ""  # 空串不冒充数字，也不在此强改 null
    assert out["containers"][0]["qty"] == "one"


def test_do_not_truncate_fractional_to_int():
    out = fill_schema({"packages_qty": "160.5"})
    assert out["packages_qty"] == "160.5"
