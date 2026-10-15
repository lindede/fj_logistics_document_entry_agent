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


@lru_cache(maxsize=1)
def _container_limits() -> dict[str, Any]:
    path = MASTERDATA_DIR / "container_limits.json"
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
    """单箱毛重/体积单位阈值（整票校验时再 × 箱数）。"""
    if not unit:
        return None
    table = _limits().get(kind, {})
    return table.get(str(unit).strip().upper())


def classify_container_size(type_str: Optional[str]) -> str:
    """箱型归类：20 / 40 / 40hq / default（未知）。"""
    if not type_str or not str(type_str).strip():
        return "default"
    t = re.sub(r"[\s'\"]+", "", str(type_str).upper())
    if any(k in t for k in ("HQ", "HC", "HIGHCUBE", "HIGH-CUBE")):
        return "40hq"
    if "45" in t:
        return "40hq"
    if "40" in t:
        return "40"
    if "20" in t:
        return "20"
    return "default"


def measurement_cbm_per_box(type_str: Optional[str]) -> float:
    """单箱体积上限（CBM）。20→50，40→80，40HQ→100，未知→50。"""
    table = _container_limits().get("measurement_cbm_per_box") or {}
    key = classify_container_size(type_str)
    if key in table:
        return float(table[key])
    return float(table.get("default", 50))


def iter_container_lines(
    data: dict[str, Any],
) -> list[tuple[Optional[str], int]]:
    """[(type, qty), ...]；无有效 qty 的行跳过。"""
    containers = data.get("containers")
    if not isinstance(containers, list):
        return []
    lines: list[tuple[Optional[str], int]] = []
    for item in containers:
        if not isinstance(item, dict):
            continue
        q = item.get("qty")
        if q is None:
            continue
        try:
            qty = int(q)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        ctype = item.get("type")
        lines.append((str(ctype) if ctype is not None else None, qty))
    return lines


def total_container_qty(data: dict[str, Any]) -> Optional[int]:
    lines = iter_container_lines(data)
    if not lines:
        return None
    return sum(q for _, q in lines)


def max_measurement_cbm_total(data: dict[str, Any]) -> Optional[float]:
    """整票体积上限 = Σ(单箱上限 × qty)。无箱量时 None。"""
    lines = iter_container_lines(data)
    if not lines:
        return None
    return sum(measurement_cbm_per_box(t) * q for t, q in lines)
