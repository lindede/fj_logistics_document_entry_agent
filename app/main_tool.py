"""仅 Tool 服务入口：APP_ROLE=tool。"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ROLE", "tool")

from app.main import app  # noqa: E402

__all__ = ["app"]
