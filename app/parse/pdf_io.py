from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from pypdf import PdfReader

from app.config import ROOT

# 远程 PDF：防滥用
_MAX_REMOTE_BYTES = 20 * 1024 * 1024
_REMOTE_TIMEOUT_S = 30.0
_URL_RE = re.compile(r"^https?://", re.I)


def _filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path or "")
    name = Path(path).name
    return name if name.lower().endswith(".pdf") else "remote.pdf"


def _fetch_remote_pdf(url: str) -> tuple[bytes, str]:
    import httpx

    try:
        with httpx.Client(follow_redirects=True, timeout=_REMOTE_TIMEOUT_S) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > _MAX_REMOTE_BYTES:
                        raise ValueError(
                            f"remote PDF exceeds {_MAX_REMOTE_BYTES} bytes limit"
                        )
                    chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise ValueError(f"failed to download PDF: {exc}") from exc

    data = b"".join(chunks)
    if not data:
        raise ValueError("remote PDF is empty")
    return data, _filename_from_url(url)


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
        fp = str(file_path).strip()
        if _URL_RE.match(fp):
            return _fetch_remote_pdf(fp)

        path = Path(fp)
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        else:
            path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"file not found: {path}")
        if not path.is_file():
            raise ValueError(f"not a file: {path}")
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
