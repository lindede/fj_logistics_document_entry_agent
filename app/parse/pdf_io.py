from __future__ import annotations

import base64
import io
from pathlib import Path

from pypdf import PdfReader

from app.config import ROOT


def resolve_pdf_input(
    file_path: str | None = None, base64_pdf: str | None = None
) -> tuple[bytes, str]:
    if base64_pdf and str(base64_pdf).strip():
        raw = str(base64_pdf).strip()
        if "," in raw and raw.lower().startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            data = base64.b64decode(raw, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("invalid base64_pdf") from exc
        return data, "upload.pdf"
    if file_path and str(file_path).strip():
        path = Path(file_path)
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"file not found: {path}")
        return path.read_bytes(), path.name
    raise ValueError("either file_path or base64_pdf is required")


def assert_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF"):
        raise ValueError("not a valid PDF (missing %PDF header)")
    try:
        PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"cannot open PDF: {exc}") from exc


def extract_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)
