from __future__ import annotations

from typing import Any

from app.masterdata import (
    is_known_vessel,
    match_port,
    max_measurement_cbm_total,
    total_container_qty,
    weight_limits,
)
from app.models import FieldIssue

# 结构/类型（必填、containers、freight∈PCE 等）统一由 schema_check.STRUCT-SCHEMA 负责，此处只留 BR-*。


def br_01_ports_differ(data: dict[str, Any]) -> list[FieldIssue]:
    pol = (data.get("port_of_loading") or "").strip().upper()
    pod = (data.get("port_of_discharge") or "").strip().upper()
    if not pol or not pod:
        return []
    # 归一化去掉分隔符再比；同时比代码段
    def codes(s: str) -> set[str]:
        import re

        return set(re.findall(r"\b[A-Z]{5}\b", s))

    same = pol == pod or (codes(pol) and codes(pol) == codes(pod))
    if same:
        return [
            FieldIssue(
                field="port_of_loading",
                rule="BR-01",
                level="FAIL",
                message="port_of_loading must differ from port_of_discharge",
            )
        ]
    return []


def br_02_ranges(data: dict[str, Any]) -> list[FieldIssue]:
    """毛重/体积：表内为单箱上限；整票上限 = 单箱 × 箱数（体积再按箱型取单箱上限）。"""
    issues: list[FieldIssue] = []
    qty = total_container_qty(data)
    gw = data.get("gross_weight")
    wu = data.get("weight_unit")
    if gw is not None:
        try:
            gwf = float(gw)
        except (TypeError, ValueError):
            issues.append(
                FieldIssue(
                    field="gross_weight",
                    rule="BR-02",
                    level="FAIL",
                    message=f"gross_weight must be numeric: {gw}",
                )
            )
            gwf = None
        if gwf is not None:
            if gwf <= 0:
                issues.append(
                    FieldIssue(
                        field="gross_weight",
                        rule="BR-02",
                        level="FAIL",
                        message="gross_weight must be > 0",
                    )
                )
            lim = weight_limits("gross_weight", wu)
            if lim and gwf > 0:
                per_max = float(lim["max"])
                per_min = float(lim["min"])
                if qty:
                    max_total = per_max * qty
                    min_total = per_min
                    if not (min_total <= gwf <= max_total):
                        issues.append(
                            FieldIssue(
                                field="gross_weight",
                                rule="BR-02",
                                level="FAIL",
                                message=(
                                    f"gross_weight {gwf} {wu} out of range "
                                    f"{min_total}–{max_total} "
                                    f"(per-box max {per_max} × {qty} containers)"
                                ),
                            )
                        )
                elif not (per_min <= gwf <= per_max):
                    # 无箱量：退回按单箱上限卡一道，避免飞数
                    issues.append(
                        FieldIssue(
                            field="gross_weight",
                            rule="BR-02",
                            level="FAIL",
                            message=(
                                f"gross_weight {gwf} {wu} out of range "
                                f"{per_min}–{per_max} (no container qty; per-box limit)"
                            ),
                        )
                    )
    meas = data.get("measurement")
    mu = data.get("measurement_unit")
    if meas is not None:
        try:
            mf = float(meas)
        except (TypeError, ValueError):
            issues.append(
                FieldIssue(
                    field="measurement",
                    rule="BR-02",
                    level="FAIL",
                    message=f"measurement must be numeric: {meas}",
                )
            )
            mf = None
        if mf is not None:
            if mf <= 0:
                issues.append(
                    FieldIssue(
                        field="measurement",
                        rule="BR-02",
                        level="FAIL",
                        message="measurement must be > 0",
                    )
                )
            unit_u = str(mu or "").strip().upper()
            if unit_u in {"CBM", "M3"} and mf > 0:
                max_total = max_measurement_cbm_total(data)
                if max_total is not None:
                    if mf > max_total:
                        issues.append(
                            FieldIssue(
                                field="measurement",
                                rule="BR-02",
                                level="FAIL",
                                message=(
                                    f"measurement {mf} {mu} exceeds max {max_total} "
                                    f"(per-box CBM by container type × qty)"
                                ),
                            )
                        )
                else:
                    # 无箱量：未知箱型单箱默认 50 CBM
                    per_default = 50.0
                    if mf > per_default:
                        issues.append(
                            FieldIssue(
                                field="measurement",
                                rule="BR-02",
                                level="FAIL",
                                message=(
                                    f"measurement {mf} {mu} exceeds max {per_default} "
                                    f"(no container qty; default per-box CBM)"
                                ),
                            )
                        )
            elif unit_u:
                lim = weight_limits("measurement", mu)
                if lim and not (lim["min"] <= mf <= lim["max"]):
                    issues.append(
                        FieldIssue(
                            field="measurement",
                            rule="BR-02",
                            level="FAIL",
                            message=(
                                f"measurement {mf} {mu} out of range "
                                f"{lim['min']}–{lim['max']}"
                            ),
                        )
                    )
    return issues


def br_03_vessel(data: dict[str, Any]) -> list[FieldIssue]:
    vessel = data.get("vessel")
    if not vessel:
        return []
    if not is_known_vessel(str(vessel)):
        return [
            FieldIssue(
                field="vessel",
                rule="BR-03",
                level="WARN",
                message=f"vessel '{vessel}' not in whitelist",
            )
        ]
    return []


def br_04_shipper_consignee(data: dict[str, Any]) -> list[FieldIssue]:
    s = (data.get("shipper") or "").strip().upper()
    c = (data.get("consignee") or "").strip().upper()
    if s and c and s == c:
        return [
            FieldIssue(
                field="shipper",
                rule="BR-04",
                level="WARN",
                message="shipper equals consignee",
            )
        ]
    return []


def br_05_no_fabricate(data: dict[str, Any]) -> list[FieldIssue]:
    """防 LLM 把无唛头编成 N/M；空串等结构问题交给 STRUCT-SCHEMA。"""
    marks = data.get("marks")
    if isinstance(marks, str) and marks.strip().upper() in {"N/M", "NM", "N.M"}:
        return [
            FieldIssue(
                field="marks",
                rule="BR-05",
                level="FAIL",
                message="marks must be null when no evidence (do not use N/M)",
            )
        ]
    return []


def br_06_ports_whitelist(data: dict[str, Any]) -> list[FieldIssue]:
    issues: list[FieldIssue] = []
    for field in ("port_of_loading", "port_of_discharge"):
        val = data.get(field)
        if not val:
            continue
        if match_port(str(val)) is None:
            issues.append(
                FieldIssue(
                    field=field,
                    rule="BR-06",
                    level="WARN",
                    message=f"{field} '{val}' not matched in port whitelist",
                )
            )
    return issues
