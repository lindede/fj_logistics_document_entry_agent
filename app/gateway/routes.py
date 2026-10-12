from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent.session import session_manager
from app.config import SUBMIT_STRATEGY
from app.models import ParseBookingRequest, SessionActionRequest
from app.observe import timed

router = APIRouter(prefix="/api")


class StrategyBody(BaseModel):
    submit_strategy: str


@router.post("/parse_booking")
@timed("api_parse_booking")
def parse_booking(body: ParseBookingRequest) -> dict[str, Any]:
    try:
        result = session_manager.parse_and_validate(body.file_path, body.base64_pdf)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "raw_extracted_data": result["raw_extracted_data"],
        "validated_data": result["validated_data"],
        "validation_report": result["validation_report"],
        "doc_type_ok": result.get("doc_type_ok", True),
        "elapsed_ms": result.get("elapsed_ms", 0),
    }


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


@router.get("/mcp/tools")
def mcp_tools() -> dict[str, Any]:
    """MCP 风格 Tool 描述（与 HTTP 共用核心）。"""
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
                "endpoint": "/api/parse_booking",
            }
        ]
    }
