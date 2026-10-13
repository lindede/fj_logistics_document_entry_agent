from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent.session import session_manager
from app.config import SUBMIT_STRATEGY
from app.models import ParseBookingRequest, SessionActionRequest
from app.observe import timed
from app.validate.schema_check import load_booking_schema

router = APIRouter(prefix="/api")


class StrategyBody(BaseModel):
    submit_strategy: str


@router.post("/parse_booking")
@timed("api_parse_booking")
def parse_booking(body: ParseBookingRequest) -> dict[str, Any]:
    """HTTP 扁平三件套：由 BookingRecord 投影，不另写一套解析逻辑。"""
    from app.booking import process_booking, triple_from_record

    try:
        record = process_booking(file_path=body.file_path, base64_pdf=body.base64_pdf)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return triple_from_record(record)


@router.get("/session")
def get_session() -> dict[str, Any]:
    return session_manager.snapshot()


@router.post("/session/action")
def session_action(body: SessionActionRequest) -> dict[str, Any]:
    try:
        return session_manager.handle(
            action=body.action,
            text=body.text,
            file_path=body.file_path,
            base64_pdf=body.base64_pdf,
            patches=body.patches,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/session/upload")
async def session_upload(
    file: UploadFile = File(...),
    text: Optional[str] = Form(None),
) -> dict[str, Any]:
    data = await file.read()
    import base64

    b64 = base64.b64encode(data).decode("ascii")
    return session_manager.handle(
        action="open",
        text=text,
        base64_pdf=b64,
    )


@router.post("/config/submit_strategy")
def set_strategy(body: StrategyBody) -> dict[str, Any]:
    strategy = body.submit_strategy.lower()
    if strategy not in {"manual", "auto_on_pass"}:
        raise HTTPException(status_code=400, detail="invalid strategy")
    session_manager.submit_strategy = strategy
    return {"submit_strategy": strategy}


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "submit_strategy": SUBMIT_STRATEGY}


@router.get("/schemas/booking_data")
def get_booking_data_schema() -> dict[str, Any]:
    """供前端/联调读取业务字段 JSON Schema（HTTP 出参契约另议）。"""
    return load_booking_schema()


@router.get("/mcp/tools")
def mcp_tools() -> dict[str, Any]:
    """MCP 风格 Tool 描述（与 HTTP 共用核心）。"""
    booking_schema = load_booking_schema()
    return {
        "tools": [
            {
                "name": "parse_booking",
                "description": "Parse a booking PDF and run business validation",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "base64_pdf": {"type": "string"},
                    },
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "raw_extracted_data": booking_schema,
                        "validated_data": booking_schema,
                        "validation_report": {"type": "object"},
                        "doc_type_ok": {"type": "boolean"},
                    },
                    "required": [
                        "raw_extracted_data",
                        "validated_data",
                        "validation_report",
                    ],
                },
                "endpoint": "/api/parse_booking",
            }
        ]
    }
