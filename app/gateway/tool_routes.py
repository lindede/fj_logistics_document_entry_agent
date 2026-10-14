"""Tool 服务路由：解析+校验门面（供 Agent / 外部 HTTP 调用）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.booking import process_booking, triple_from_record
from app.config import SUBMIT_STRATEGY
from app.models import ParseBookingRequest
from app.observe import timed
from app.validate.schema_check import load_booking_schema

router = APIRouter(prefix="/api")


@router.post("/parse_booking")
@timed("api_parse_booking")
def parse_booking(body: ParseBookingRequest) -> dict[str, Any]:
    try:
        record = process_booking(file_path=body.file_path, base64_pdf=body.base64_pdf)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return triple_from_record(record)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "role": "tool", "submit_strategy": SUBMIT_STRATEGY}


@router.get("/schemas/booking_data")
def get_booking_data_schema() -> dict[str, Any]:
    return load_booking_schema()


@router.get("/mcp/tools")
def mcp_tools() -> dict[str, Any]:
    """MCP 风格 Tool 描述（非标准 MCP 协议；完全体 MCP 另议）。"""
    booking_schema = load_booking_schema()
    return {
        "tools": [
            {
                "name": "parse_booking",
                "description": "Parse a booking PDF and run business validation",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Local path or http(s) URL to PDF",
                        },
                        "base64_pdf": {"type": "string"},
                    },
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "raw_extracted_data": booking_schema,
                        "normalized_data": booking_schema,
                        "llm_analysis": {"type": "string"},
                        "validated_data": booking_schema,
                        "validation_report": {"type": "object"},
                        "doc_type_ok": {"type": "boolean"},
                    },
                    "required": [
                        "raw_extracted_data",
                        "normalized_data",
                        "validated_data",
                        "validation_report",
                    ],
                },
                "endpoint": "/api/parse_booking",
            }
        ]
    }
