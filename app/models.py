from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ContainerItem(BaseModel):
    type: str
    qty: int


class BookingData(BaseModel):
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    notify_party: Optional[str] = None
    vessel: Optional[str] = None
    voyage: Optional[str] = ""
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    containers: Optional[list[ContainerItem]] = None
    packages_qty: Optional[int] = None
    packages_unit: Optional[str] = None
    goods_desc: Optional[str] = None
    gross_weight: Optional[float] = None
    weight_unit: Optional[str] = None
    measurement: Optional[float] = None
    measurement_unit: Optional[str] = None
    hs_code: Optional[str] = None
    marks: Optional[str] = None
    freight: Optional[str] = None


class FieldIssue(BaseModel):
    field: str
    rule: str
    level: Literal["PASS", "WARN", "FAIL", "INFO"]
    message: str


class ValidationReport(BaseModel):
    overall: Literal["PASS", "WARN", "FAIL"]
    issues: list[FieldIssue] = Field(default_factory=list)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    suggested_action: str = ""
    low_confidence_fields: list[str] = Field(default_factory=list)


class ParseBookingRequest(BaseModel):
    file_path: Optional[str] = None
    base64_pdf: Optional[str] = None


class ParseBookingResponse(BaseModel):
    raw_extracted_data: dict[str, Any]
    validated_data: dict[str, Any]
    validation_report: ValidationReport
    doc_type_ok: bool = True
    elapsed_ms: float = 0.0


class SessionActionRequest(BaseModel):
    action: str
    text: Optional[str] = None
    file_path: Optional[str] = None
    base64_pdf: Optional[str] = None
    patches: Optional[dict[str, Any]] = None


class BookingRecord(BaseModel):
    session_id: str
    status: str
    raw_extracted_data: Optional[dict[str, Any]] = None
    validated_data: Optional[dict[str, Any]] = None
    validation_report: Optional[ValidationReport] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)
    filename: Optional[str] = None
    message: Optional[str] = None
