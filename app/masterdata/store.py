from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Optional

from app.config import MASTERDATA_DIR


@lru_cache(maxsize=1)
def _vessels() -> set[str]:
    path = MASTERDATA_DIR / "vessels.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {v.strip().upper() for v in data.get("vessels", [])}


@lru_cache(maxsize=1)
def _ports() -> list[dict[str, Any]]:
    path = MASTERDATA_DIR / "ports.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("ports", [])


@lru_cache(maxsize=1)
def _limits() -> dict[str, Any]:
    path = MASTERDATA_DIR / "weight_limits.json"
    return json.loads(path.read_text(encoding="utf-8"))


def is_known_vessel(name: Optional[str]) -> bool:
    if not name or not str(name).strip():
        return False
    return str(name).strip().upper() in _vessels()


def match_port(text: Optional[str]) -> Optional[dict[str, Any]]:
    if not text or not str(text).strip():
        return None
    raw = str(text).upper()
    compact = re.sub(r"[^A-Z0-9]", "", raw)
    for port in _ports():
        code = str(port.get("code", "")).upper()
        name = str(port.get("name", "")).upper()
        aliases = [str(a).upper() for a in port.get("aliases", [])]
        tokens = [code, name, *aliases]
        for token in tokens:
            if not token:
                continue
            if token in raw or re.sub(r"[^A-Z0-9]", "", token) in compact:
                return port
    return None


def weight_limits(kind: str, unit: Optional[str]) -> Optional[dict[str, float]]:
    if not unit:
        return None
    table = _limits().get(kind, {})
    return table.get(str(unit).strip().upper())
