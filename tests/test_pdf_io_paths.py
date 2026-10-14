"""file_path：相对/绝对本地路径 + http(s) 远程。"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config import ROOT
from app.parse.pdf_io import resolve_pdf_input

SAMPLE = ROOT / "data/samples/BKG.pdf"


def test_relative_local_path():
    data, name = resolve_pdf_input(file_path="data/samples/BKG.pdf")
    assert data.startswith(b"%PDF")
    assert name == "BKG.pdf"


def test_absolute_local_path():
    data, name = resolve_pdf_input(file_path=str(SAMPLE.resolve()))
    assert data.startswith(b"%PDF")
    assert name == "BKG.pdf"


def test_missing_local_path():
    with pytest.raises(FileNotFoundError):
        resolve_pdf_input(file_path="data/samples/__no_such__.pdf")


def test_remote_http_url(monkeypatch):
    pdf = SAMPLE.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://example.com/")
        return httpx.Response(200, content=pdf)

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("httpx.Client", client_factory)
    data, name = resolve_pdf_input(
        file_path="https://example.com/files/BKG.pdf"
    )
    assert data.startswith(b"%PDF")
    assert name == "BKG.pdf"


def test_remote_too_large(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF" + b"x" * (21 * 1024 * 1024))

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("httpx.Client", client_factory)
    with pytest.raises(ValueError, match="exceeds"):
        resolve_pdf_input(file_path="https://example.com/big.pdf")
