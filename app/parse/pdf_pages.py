from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DEBUG_DIR, LLM_VISION_ZOOM, PARSE_DEBUG_DUMP

logger = logging.getLogger("fj.parse")


def pdf_pages_as_png_data_urls(
    pdf_bytes: bytes, zoom: float | None = None
) -> tuple[list[str], list[str]]:
    """将 PDF 每页渲染为 PNG data URL。

    返回 (data_urls, debug_png_paths)。
    PARSE_DEBUG_DUMP 开启时额外把 PNG 落到 DEBUG_DIR/vision_* /。
    """
    import fitz

    z = float(zoom if zoom is not None else LLM_VISION_ZOOM)
    if z <= 0:
        z = 1.5
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    urls: list[str] = []
    debug_paths: list[str] = []
    dump_dir: Path | None = None
    if PARSE_DEBUG_DUMP:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dump_dir = DEBUG_DIR / f"vision_{ts}_z{z:g}"
        dump_dir.mkdir(parents=True, exist_ok=True)

    matrix = fitz.Matrix(z, z)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        png = pix.tobytes("png")
        b64 = base64.b64encode(png).decode("ascii")
        urls.append(f"data:image/png;base64,{b64}")
        if dump_dir is not None:
            path = dump_dir / f"page_{i + 1:02d}.png"
            path.write_bytes(png)
            debug_paths.append(str(path))

    if dump_dir is not None:
        logger.info(
            "PARSE_DEBUG_DUMP vision pages → %s (%d pages, zoom=%g)",
            dump_dir,
            len(debug_paths),
            z,
        )
    return urls, debug_paths


def vision_user_content(page_data_urls: list[str], prompt: str) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for url in page_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    content.append({"type": "text", "text": prompt})
    return content
