"""分阶段 LLM 输出解析。"""

from app.parse.extract import (
    _extract_llm_analysis,
    _normalize_llm_fields,
    _parse_llm_json_content,
    _parse_llm_response,
)


def test_parse_pure_json():
    out = _parse_llm_json_content('{"shipper":"A","voyage":"","freight":"P"}')
    assert out["shipper"] == "A"
    assert out["freight"] == "P"


def test_parse_staged_analysis_then_json():
    content = """
### ANALYSIS
船名与航次：BY MSC ETD:11-14
通知方：TENV

### JSON
{"shipper":"S","consignee":"C","notify_party":"TENV","vessel":"MSC","voyage":"","freight":"P"}
"""
    out = _parse_llm_json_content(content)
    assert out["notify_party"] == "TENV"
    assert out["vessel"] == "MSC"
    assert out["voyage"] == ""
    analysis = _extract_llm_analysis(content)
    assert analysis is not None
    assert "MSC" in analysis
    assert "TENV" in analysis


def test_parse_llm_response_keeps_raw_unnormalized():
    content = """
### ANALYSIS
运费写的 Prepaid

### JSON
{"freight":"预付金额 Prepaid","marks":"N/M","voyage":null}
"""
    analysis, raw = _parse_llm_response(content)
    assert analysis and "Prepaid" in analysis
    assert raw["freight"] == "预付金额 Prepaid"
    assert raw["marks"] == "N/M"
    assert raw["voyage"] is None
    normalized = _normalize_llm_fields(raw)
    assert normalized["freight"] == "P"
    assert normalized["marks"] is None
    assert normalized["voyage"] == ""


def test_parse_staged_with_code_fence():
    content = """
### ANALYSIS
ok

### JSON
```json
{"vessel":"MSC","voyage":"","marks":null}
```
"""
    out = _parse_llm_json_content(content)
    assert out["vessel"] == "MSC"
    assert out["marks"] is None
