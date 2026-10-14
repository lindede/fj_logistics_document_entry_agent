"""parse_booking Tool：优先 HTTP 调 Tool 服务；非 agent 角色可本地门面。"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.config import APP_ROLE, TOOL_BASE_URL, TOOL_HTTP_TIMEOUT_S

logger = logging.getLogger("fj.tools")


class ParseBookingInput(BaseModel):
    file_path: Optional[str] = Field(default=None, description="本地路径或 http(s) PDF URL")
    base64_pdf: Optional[str] = Field(default=None, description="PDF base64（可含 data: 前缀）")


def _local_parse_booking(
    file_path: str | None = None, base64_pdf: str | None = None
) -> dict[str, Any]:
    from app.booking import process_booking, triple_from_record

    record = process_booking(file_path=file_path, base64_pdf=base64_pdf)
    return triple_from_record(record)


def _http_parse_booking(
    file_path: str | None = None, base64_pdf: str | None = None
) -> dict[str, Any]:
    if not TOOL_BASE_URL:
        raise RuntimeError("TOOL_BASE_URL is not set")
    url = f"{TOOL_BASE_URL}/api/parse_booking"
    payload = {"file_path": file_path, "base64_pdf": base64_pdf}
    # trust_env=False：避免本机 HTTP_PROXY 把 127.0.0.1 打成 502
    with httpx.Client(timeout=TOOL_HTTP_TIMEOUT_S, trust_env=False) as client:
        resp = client.post(url, json=payload)
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"tool parse_booking HTTP {resp.status_code}: {detail}")
        return resp.json()


def invoke_parse_booking(
    file_path: str | None = None,
    base64_pdf: str | None = None,
) -> dict[str, Any]:
    """
    Agent 开票解析入口。
    - 配置了 TOOL_BASE_URL → 只走 HTTP Tool 服务
    - APP_ROLE=agent 且无 URL → 报错（禁止静默本地解析）
    - 其它（all/tool/测试）→ 可本地门面
    """
    role = (APP_ROLE or "all").lower()
    if TOOL_BASE_URL:
        logger.info("parse_booking via HTTP tool %s", TOOL_BASE_URL)
        return _http_parse_booking(file_path=file_path, base64_pdf=base64_pdf)
    if role == "agent":
        raise RuntimeError(
            "APP_ROLE=agent 时必须配置 TOOL_BASE_URL，禁止 Agent 本地调用解析实现"
        )
    logger.info("parse_booking via local facade (APP_ROLE=%s)", role)
    return _local_parse_booking(file_path=file_path, base64_pdf=base64_pdf)


def get_parse_booking_tool() -> StructuredTool:
    """LangChain StructuredTool，供 Agent/图统一 invoke。"""
    return StructuredTool.from_function(
        name="parse_booking",
        description=(
            "Parse a booking/shipping-order PDF and run validation. "
            "Provide file_path (local or http URL) or base64_pdf. "
            "Returns raw_extracted_data, normalized_data, llm_analysis, "
            "validated_data, validation_report."
        ),
        func=lambda file_path=None, base64_pdf=None: invoke_parse_booking(
            file_path=file_path, base64_pdf=base64_pdf
        ),
        args_schema=ParseBookingInput,
    )
