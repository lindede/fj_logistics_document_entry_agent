from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_parse_booking_sample():
    r = client.post(
        "/api/parse_booking",
        json={"file_path": "data/samples/BKG.pdf"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "raw_extracted_data" in body
    assert "validated_data" in body
    assert "validation_report" in body
    assert body["validated_data"]["vessel"] == "MSC"


def test_session_flow_void():
    client.post("/api/session/action", json={"action": "void"})
    r = client.post(
        "/api/session/action",
        json={"action": "open", "file_path": "data/samples/BKG.pdf"},
    )
    assert r.status_code == 200
    assert r.json()["status"] in {"AwaitConfirm", "AwaitHuman"}
    r2 = client.post("/api/session/action", json={"action": "void"})
    assert r2.json()["status"] == "Idle"


def test_mcp_tools():
    r = client.get("/api/mcp/tools")
    assert r.status_code == 200
    assert r.json()["tools"][0]["name"] == "parse_booking"
