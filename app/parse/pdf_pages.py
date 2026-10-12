from __future__ import annotations

import base64
from typing import Any


def pdf_pages_as_png_data_urls(pdf_bytes: bytes, zoom: float = 1.5) -> list[str]:
    """将 PDF 每页渲染为 PNG data URL，供多模态模型保留版面。"""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    urls: list[str] = []
    matrix = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
        urls.append(f"data:image/png;base64,{b64}")
    return urls


def vision_user_content(page_data_urls: list[str], prompt: str) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for url in page_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    content.append({"type": "text", "text": prompt})
    return content
