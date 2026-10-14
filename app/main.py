from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import APP_ROLE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

role = (APP_ROLE or "all").lower()
app = FastAPI(
    title="FJ Logistics Document Entry",
    version=__version__,
    description=f"单证录入 Demo（APP_ROLE={role}）",
)

if role in {"all", "tool"}:
    from app.gateway.tool_routes import router as tool_router

    app.include_router(tool_router)

if role in {"all", "agent"}:
    from app.gateway.routes import router as agent_router

    app.include_router(agent_router)

    STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")
