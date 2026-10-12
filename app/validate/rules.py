from __future__ import annotations

from typing import Any

from app.config import REQUIRED_KEYS
from app.masterdata import is_known_vessel, match_port, weight_limits
from app.models import FieldIssue


def check_structure(data: dict[str, Any]) -> list[FieldIssue]:
    issues: list[FieldIssue] = []
    for key in REQUIRED_KEYS:
        val = data.get(key)
        empty = val is None or val == "" or val == []
        if empty:
            issues.append(
                FieldIssue(
                    field=key,
                    rule="STRUCT-REQUIRED",
                    level="FAIL",
                    message=f"required field missing: {key}",
                )
            )
    containers = data.get("containers")
    if containers is not None:
        if not isinstance(containers, list):
            issues.append(
                FieldIssue(
                    field="containers",
                    rule="STRUCT-CONTAINERS",
                    level="FAIL",
                    message="containers must be an array",
                )
            )
        else:
            for i, item in enumerate(containers):
                if not isinstance(item, dict) or "type" not in item or "qty" not in item:
                    issues.append(
                        FieldIssue(
                            field="containers",
                            rule="STRUCT-CONTAINERS",
                            level="FAIL",
                            message=f"containers[{i}] needs type and qty",
                        )
                    )
    freight = data.get("freight")
    if freight is not None and str(freight).upper() not in {"P", "C", "E"}:
        issues.append(
            FieldIssue(
                field="freight",
                rule="STRUCT-FREIGHT",
                level="FAIL",
                message="freight must be P/C/E or null",
            )
        )
    return issues


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
    issues: list[FieldIssue] = []
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
                    message="gross_weight must be numeric",
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
            if lim and not (lim["min"] <= gwf <= lim["max"]):
                issues.append(
                    FieldIssue(
                        field="gross_weight",
                        rule="BR-02",
                        level="FAIL",
                        message=f"gross_weight {gwf} {wu} out of range {lim['min']}–{lim['max']}",
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
                    message="measurement must be numeric",
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
            lim = weight_limits("measurement", mu)
            if lim and not (lim["min"] <= mf <= lim["max"]):
                issues.append(
                    FieldIssue(
                        field="measurement",
                        rule="BR-02",
                        level="FAIL",
                        message=f"measurement {mf} {mu} out of range {lim['min']}–{lim['max']}",
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
    issues: list[FieldIssue] = []
    marks = data.get("marks")
    if isinstance(marks, str) and marks.strip().upper() in {"N/M", "NM", "N.M", ""}:
        issues.append(
            FieldIssue(
                field="marks",
                rule="BR-05",
                level="FAIL",
                message="marks must be null when no evidence (do not use N/M or empty string)",
            )
        )
    for key in ("hs_code", "marks", "freight"):
        if data.get(key) == "":
            issues.append(
                FieldIssue(
                    field=key,
                    rule="BR-05",
                    level="FAIL",
                    message=f"{key} must be null when absent, not empty string",
                )
            )
    return issues


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
