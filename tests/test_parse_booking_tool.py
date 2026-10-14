"""parse_booking Tool：本地门面 + HTTP 客户端。"""

from __future__ import annotations

import pytest

from app.tools.parse_booking_client import (
    get_parse_booking_tool,
    invoke_parse_booking,
)


def test_local_invoke_parse_booking(monkeypatch):
    monkeypatch.setattr("app.tools.parse_booking_client.TOOL_BASE_URL", "")
    monkeypatch.setattr("app.tools.parse_booking_client.APP_ROLE", "all")
    out = invoke_parse_booking(file_path="data/samples/BKG.pdf")
    assert out["validated_data"]["vessel"] == "MSC"
    assert "validation_report" in out


def test_agent_role_requires_tool_url(monkeypatch):
    monkeypatch.setattr("app.tools.parse_booking_client.TOOL_BASE_URL", "")
    monkeypatch.setattr("app.tools.parse_booking_client.APP_ROLE", "agent")
    with pytest.raises(RuntimeError, match="TOOL_BASE_URL"):
        invoke_parse_booking(file_path="data/samples/BKG.pdf")


def test_http_invoke(monkeypatch):
    monkeypatch.setattr(
        "app.tools.parse_booking_client.TOOL_BASE_URL", "http://tool.test"
    )

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "raw_extracted_data": {"vessel": "MSC"},
                "validated_data": {"vessel": "MSC"},
                "validation_report": {"overall": "PASS"},
                "doc_type_ok": True,
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            assert url.endswith("/api/parse_booking")
            return FakeResp()

    monkeypatch.setattr("app.tools.parse_booking_client.httpx.Client", FakeClient)
    out = invoke_parse_booking(file_path="data/samples/BKG.pdf")
    assert out["validated_data"]["vessel"] == "MSC"


def test_langchain_structured_tool():
    tool = get_parse_booking_tool()
    assert tool.name == "parse_booking"
    out = tool.invoke({"file_path": "data/samples/BKG.pdf"})
    assert out["validated_data"]["vessel"] == "MSC"
