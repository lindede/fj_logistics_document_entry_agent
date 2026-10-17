"""html_mix：struct + LLM 对照，不一致记 MIX-DIFF。"""

from __future__ import annotations

import json
from pathlib import Path

from app.booking.process import process_booking
from app.parse.extract import _normalize_llm_fields, llm_extract_from_pdf, parse_pdf_bytes
from app.parse.html_mix import field_values_equal, mix_diff_issues
from app.parse.html_struct import extract_html_struct

_BKG = Path("data/samples/BKG.pdf")
_GOLD = json.loads(Path("data/gold/bkg_sample.json").read_text(encoding="utf-8"))


def test_field_values_equal_voyage_and_empty():
    assert field_values_equal("voyage", "", None)
    assert field_values_equal("marks", None, None)
    assert not field_values_equal("gross_weight", "2560OKGS", 25600)
    assert field_values_equal(
        "containers",
        [{"type": "40HQ", "qty": 1}],
        [{"type": "40HQ", "qty": 1}],
    )


def test_mix_diff_issues_message_keeps_both_sides():
    struct = _normalize_llm_fields({"gross_weight": "2560OKGS", "weight_unit": "KGS"})
    llm = _normalize_llm_fields({"gross_weight": 25600, "weight_unit": "KGS"})
    issues = mix_diff_issues(struct, llm)
    by_field = {i.field: i for i in issues}
    assert by_field["gross_weight"].rule == "MIX-DIFF"
    assert by_field["gross_weight"].level == "WARN"
    assert "2560OKGS" in by_field["gross_weight"].message
    assert "25600" in by_field["gross_weight"].message


def test_html_mix_uses_llm_primary_and_flags_goods_desc(monkeypatch):
    """BKG：struct 货名带中文，LLM 金标准只有英文 → MIX-DIFF；主结果用 LLM。"""
    monkeypatch.setenv("PARSE_BACKEND", "llm")
    monkeypatch.setenv("LLM_INPUT_MODE", "html_mix")
    monkeypatch.setattr("app.parse.extract.has_llm_key", lambda: True)

    llm_payload = dict(_GOLD)
    # 故意与 struct 船名可能一致；货名只给英文，制造与 struct 的差异
    llm_payload["goods_desc"] = "Rechargeable Li-ion Cell"

    def fake_call_chat(client, messages, *, use_json_format, model=None):
        return (
            "### ANALYSIS\nfixture\n### JSON\n"
            + json.dumps(llm_payload, ensure_ascii=False)
        )

    monkeypatch.setattr("app.parse.extract._call_chat", fake_call_chat)
    monkeypatch.setattr("app.parse.extract.make_openai_client", lambda: object())

    packed = llm_extract_from_pdf(_BKG.read_bytes())
    assert packed["raw_extracted_data"]["goods_desc"] == "Rechargeable Li-ion Cell"
    assert packed["html_struct_raw"] is not None
    assert "可充电锂离子电芯" in packed["html_struct_raw"]["goods_desc"]
    fields = {i["field"] for i in packed["mix_diff_issues"]}
    assert "goods_desc" in fields

    out = parse_pdf_bytes(_BKG.read_bytes())
    assert out["backend"] == "llm:html_mix"
    assert out["normalized_data"]["goods_desc"] == "Rechargeable Li-ion Cell"
    assert any(i["field"] == "goods_desc" for i in out["mix_diff_issues"])


def test_html_mix_llm_failure_does_not_fall_back_to_struct(monkeypatch):
    monkeypatch.setenv("LLM_INPUT_MODE", "html_mix")
    monkeypatch.setattr("app.parse.extract.has_llm_key", lambda: True)
    monkeypatch.setattr("app.parse.extract.make_openai_client", lambda: object())

    def boom(*_a, **_k):
        raise RuntimeError("llm down")

    monkeypatch.setattr("app.parse.extract._call_chat", boom)
    try:
        llm_extract_from_pdf(_BKG.read_bytes())
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "html LLM 失败" in str(exc)
        assert "html_struct 已成功" in str(exc)


def test_process_booking_merges_mix_diff_as_warn(monkeypatch, tmp_path):
    monkeypatch.setenv("PARSE_BACKEND", "llm")
    monkeypatch.setenv("LLM_INPUT_MODE", "html_mix")
    monkeypatch.setenv("PARSE_DEBUG_DUMP", "false")
    monkeypatch.setattr("app.parse.extract.has_llm_key", lambda: True)
    monkeypatch.setattr("app.parse.extract.make_openai_client", lambda: object())

    # LLM 与 struct 在港口上故意不一致，保证至少一条 MIX-DIFF
    llm_payload = dict(_GOLD)
    llm_payload["port_of_loading"] = "SHANGHAI"

    def fake_call_chat(client, messages, *, use_json_format, model=None):
        return "### ANALYSIS\nx\n### JSON\n" + json.dumps(llm_payload, ensure_ascii=False)

    monkeypatch.setattr("app.parse.extract._call_chat", fake_call_chat)

    pdf = tmp_path / "BKG.pdf"
    pdf.write_bytes(_BKG.read_bytes())
    record = process_booking(file_path=str(pdf))
    report = record.validation_report
    assert report is not None
    mix = [i for i in report.issues if i.rule == "MIX-DIFF"]
    assert mix
    assert any(i.field == "port_of_loading" for i in mix)
    assert "QINGDAO" in next(i.message for i in mix if i.field == "port_of_loading")
    assert "SHANGHAI" in next(i.message for i in mix if i.field == "port_of_loading")
    # 主结果是 LLM
    assert record.validated_data["port_of_loading"] == "SHANGHAI"
    assert record.meta.get("html_struct_raw") is not None
    # 有 MIX-DIFF 时至少是 WARN（港口不一致还可能触发其它规则）
    assert report.overall in {"WARN", "FAIL"}
    if all(i.level != "FAIL" for i in report.issues if i.rule != "MIX-DIFF"):
        assert report.overall == "WARN"


def test_struct_alone_matches_gold_ports():
    """验收：BKG 的 struct 侧港口与金标准一致，供 mix 对照。"""
    raw = extract_html_struct(_BKG.read_bytes())
    data = _normalize_llm_fields(raw)
    assert data["port_of_loading"] == _GOLD["port_of_loading"]
    assert data["port_of_discharge"] == _GOLD["port_of_discharge"]
    assert data["notify_party"] == _GOLD["notify_party"]
