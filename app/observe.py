from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger("fj.obs")

F = TypeVar("F", bound=Callable[..., Any])


def timed(op: str) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                elapsed = (time.perf_counter() - t0) * 1000
                conf = None
                if isinstance(result, dict):
                    report = result.get("validation_report")
                    if isinstance(report, dict):
                        conf = report.get("field_confidence")
                    elif hasattr(report, "field_confidence"):
                        conf = report.field_confidence
                logger.info(
                    "op=%s elapsed_ms=%.1f field_confidence=%s",
                    op,
                    elapsed,
                    conf,
                )
                if isinstance(result, dict):
                    result = {**result, "elapsed_ms": elapsed}
                return result
            except Exception:
                elapsed = (time.perf_counter() - t0) * 1000
                logger.exception("op=%s failed elapsed_ms=%.1f", op, elapsed)
                raise

        return wrapper  # type: ignore[return-value]

    return deco


def metrics_stub(event: str, **kwargs: Any) -> None:
    """预留指标扩展点（ADV-02）。"""
    logger.debug("metric event=%s payload=%s", event, kwargs)


def trace_stub(span: str, **kwargs: Any) -> None:
    """预留链路追踪扩展点。"""
    logger.debug("trace span=%s payload=%s", span, kwargs)
