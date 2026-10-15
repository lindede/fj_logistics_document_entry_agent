from app.validate import validate_booking


def _base(**overrides):
    data = {
        "shipper": "A Co",
        "consignee": "B Co",
        "notify_party": "C Co",
        "vessel": "MSC",
        "voyage": "",
        "port_of_loading": "QINGDAO CNTAO",
        "port_of_discharge": "NHAVA SHEVA INNSA",
        "containers": [{"type": "40HQ", "qty": 1}],
        "packages_qty": 10,
        "packages_unit": "CTNS",
        "goods_desc": "Goods",
        "gross_weight": 1000,
        "weight_unit": "KGS",
        "measurement": 10,
        "measurement_unit": "CBM",
        "hs_code": None,
        "marks": None,
        "freight": None,
    }
    data.update(overrides)
    return data


def test_br01_fail():
    _, report = validate_booking(
        _base(port_of_discharge="QINGDAO CNTAO")
    )
    assert report.overall == "FAIL"
    assert any(i.rule == "BR-01" for i in report.issues)


def test_br02_fail():
    _, report = validate_booking(_base(gross_weight=999999))
    assert any(i.rule == "BR-02" for i in report.issues)


def test_br02_weight_scales_with_container_qty():
    # 单箱 KGS max 50000；2 箱允许到 100000
    _, report_ok = validate_booking(
        _base(
            containers=[{"type": "40HQ", "qty": 2}],
            gross_weight=90000,
            weight_unit="KGS",
        )
    )
    assert not any(
        i.rule == "BR-02" and i.field == "gross_weight" for i in report_ok.issues
    )
    _, report_bad = validate_booking(
        _base(
            containers=[{"type": "40HQ", "qty": 1}],
            gross_weight=90000,
            weight_unit="KGS",
        )
    )
    assert any(
        i.rule == "BR-02" and i.field == "gross_weight" for i in report_bad.issues
    )


def test_br02_measurement_by_container_type():
    # 40HQ 单箱 100 CBM；2 箱上限 200
    _, ok = validate_booking(
        _base(
            containers=[{"type": "40HQ", "qty": 2}],
            measurement=180,
            measurement_unit="CBM",
        )
    )
    assert not any(i.rule == "BR-02" and i.field == "measurement" for i in ok.issues)
    # 20GP 单箱 50；1 箱 60 → FAIL
    _, bad20 = validate_booking(
        _base(
            containers=[{"type": "20GP", "qty": 1}],
            measurement=60,
            measurement_unit="CBM",
        )
    )
    assert any(i.rule == "BR-02" and i.field == "measurement" for i in bad20.issues)
    # 未知箱型默认单箱 50
    _, bad_unk = validate_booking(
        _base(
            containers=[{"type": "SPECIAL", "qty": 1}],
            measurement=60,
            measurement_unit="CBM",
        )
    )
    assert any(i.rule == "BR-02" and i.field == "measurement" for i in bad_unk.issues)


def test_br03_warn():
    _, report = validate_booking(_base(vessel="ZZZ SHIP"))
    assert report.overall == "WARN"
    assert any(i.rule == "BR-03" for i in report.issues)


def test_br04_warn():
    _, report = validate_booking(_base(shipper="SAME", consignee="SAME"))
    assert any(i.rule == "BR-04" for i in report.issues)


def test_pass_sample_like():
    _, report = validate_booking(_base())
    assert report.overall in {"PASS", "WARN"}
    assert report.overall != "FAIL"
