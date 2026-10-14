"""自然语言改字段：离线走正则回退；sanitize 过滤非法 key。"""

from __future__ import annotations

from app.agent.nl_patch import _sanitize_patches, parse_nl_patches


def test_regex_fallback_kgs_to_ton(monkeypatch):
    monkeypatch.setenv("PARSE_BACKEND", "fixture")
    import app.config as cfg
    import app.agent.nl_patch as mod

    monkeypatch.setattr(cfg, "PARSE_BACKEND", "fixture")
    monkeypatch.setattr(mod, "parse_backend", lambda: "fixture")

    p = parse_nl_patches("把毛重单位从 KGS 换成 TON")
    assert p is not None
    assert p.get("weight_unit") == "TON"
    assert p.get("_convert_weight") is True


def test_sanitize_drops_unknown_keys():
    out = _sanitize_patches(
        {"vessel": "MSC", "evil": 1, "_convert_weight": True, "weight_unit": "TON"}
    )
    assert "evil" not in out
    assert out["vessel"] == "MSC"
    assert out["_convert_weight"] is True
