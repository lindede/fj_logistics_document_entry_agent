"""用 booking_data.schema.json 做试样/类型检查（只判不改）。"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from app.config import BOOKING_DATA_SCHEMA_PATH
from app.models import FieldIssue


@lru_cache(maxsize=1)
def load_booking_schema() -> dict[str, Any]:
    return json.loads(BOOKING_DATA_SCHEMA_PATH.read_text(encoding="utf-8"))


def check_schema(data: dict[str, Any] | None) -> list[FieldIssue]:
    """JSON Schema 格式校验 → FieldIssue(STRUCT-SCHEMA)。"""
    validator = Draft202012Validator(load_booking_schema())
    issues: list[FieldIssue] = []
    for err in sorted(validator.iter_errors(data or {}), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.absolute_path) or "_document"
        issues.append(
            FieldIssue(
                field=path,
                rule="STRUCT-SCHEMA",
                level="FAIL",
                message=err.message,
            )
        )
    return issues
