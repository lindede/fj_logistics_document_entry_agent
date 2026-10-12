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
