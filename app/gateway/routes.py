"""Agent 服务路由：会话 / 前端配置（解析请走 Tool 服务）。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent.session import session_manager
from app.config import SUBMIT_STRATEGY, TOOL_BASE_URL
from app.models import SessionActionRequest
from app.validate.schema_check import load_booking_schema

router = APIRouter(prefix="/api")


class StrategyBody(BaseModel):
    submit_strategy: str


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
            force=bool(body.force),
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/session/upload")
async def session_upload(
    file: UploadFile = File(...),
    text: Optional[str] = Form(None),
) -> dict[str, Any]:
    data = await file.read()
    import base64

    b64 = base64.b64encode(data).decode("ascii")
    try:
        return session_manager.handle(
            action="open",
            text=text,
            base64_pdf=b64,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/config/submit_strategy")
def set_strategy(body: StrategyBody) -> dict[str, Any]:
    strategy = body.submit_strategy.lower()
    if strategy not in {"manual", "auto_on_pass"}:
        raise HTTPException(status_code=400, detail="invalid strategy")
    session_manager.submit_strategy = strategy
    return {"submit_strategy": strategy}


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "role": "agent",
        "submit_strategy": SUBMIT_STRATEGY,
        "tool_base_url": TOOL_BASE_URL or None,
    }


@router.get("/schemas/booking_data")
def get_booking_data_schema() -> dict[str, Any]:
    """前端字段列表；Agent 进程本地读 schema，不经 Tool。"""
    return load_booking_schema()
