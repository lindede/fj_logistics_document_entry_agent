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
    """解析订舱 PDF：file_path 与 base64_pdf 至少提供一个。"""

    file_path: Optional[str] = Field(
        default=None,
        description="本地相对/绝对路径，或 http(s) PDF URL",
    )
    base64_pdf: Optional[str] = Field(
        default=None,
        description="PDF 的 base64（可含 data: 前缀）",
    )


class ParseBookingResponse(BaseModel):
    """与 process_booking → triple_from_record 实际出参对齐（供 OpenAPI /docs）。"""

    raw_extracted_data: Optional[dict[str, Any]] = Field(
        default=None, description="模型抽取原样（未 normalize）"
    )
    normalized_data: Optional[dict[str, Any]] = Field(
        default=None, description="规整后字段"
    )
    validated_data: Optional[dict[str, Any]] = Field(
        default=None, description="校验后字段（供录入）"
    )
    validation_report: Optional[ValidationReport] = Field(
        default=None, description="overall / issues / 置信度等"
    )
    llm_analysis: Optional[str] = Field(default=None, description="分阶段 ANALYSIS 叙述")
    doc_type_ok: bool = Field(default=True, description="是否判为托运/订舱单")
    filename: Optional[str] = None
    backend: Optional[str] = Field(default=None, description="解析后端标记，如 llm/fixture")


class SessionActionRequest(BaseModel):
    action: str
    text: Optional[str] = None
    file_path: Optional[str] = None
    base64_pdf: Optional[str] = None
    patches: Optional[dict[str, Any]] = None
    force: Optional[bool] = None


class BookingRecord(BaseModel):
    session_id: str
    status: str
    raw_extracted_data: Optional[dict[str, Any]] = None
    normalized_data: Optional[dict[str, Any]] = None
    llm_analysis: Optional[str] = None
    validated_data: Optional[dict[str, Any]] = None
    validation_report: Optional[ValidationReport] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)
    filename: Optional[str] = None
    message: Optional[str] = None
