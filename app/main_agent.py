"""仅 Agent 服务入口：APP_ROLE=agent（须配置 TOOL_BASE_URL）。"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ROLE", "agent")

from app.main import app  # noqa: E402

__all__ = ["app"]
