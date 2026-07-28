from typing import Literal

from pydantic import Field, model_validator

from core.contracts.common import NetworkType, StrictModel

DocumentCategory = Literal[
    "apd_plan",
    "antenna_plan",
    "elevation_plan",
    "site_plan",
    "mass_plan",
    "grounding_plan",
    "cable_route_plan",
    "adduction_plan",
    "technical_sheet",
    "equipment_list",
    "photo",
    "photomontage",
    "cad_dwg",
    "cad_dxf",
    "administrative",
    "lease_or_bail",
    "source_image",
    "psd_or_design_source",
    "unknown",
    "irrelevant",
]
Extractability = Literal["text", "image", "cad", "binary", "unsupported"]
DocumentPriority = Literal["high", "medium", "low", "ignore"]
DocumentPurpose = Literal[
    "needed_for_design",
    "useful_context",
    "administrative_reference",
    "visual_reference",
    "unsupported_but_recorded",
    "irrelevant",
]
FieldStatus = Literal["confirmed", "inferred", "missing", "conflict"]
MissingSeverity = Literal["blocking", "warning", "optional"]
ConflictResolution = Literal["selected", "unresolved", "needs_user_review"]
CadStatus = Literal["not_cad", "inventory_only", "converted", "parsed", "unsupported"]
DocumentExtractionStatus = Literal[
    "not_attempted",
    "extracted",
    "no_text",
    "unavailable",
    "unsupported",
    "failed",
    "inventory_only",
]
ToolAvailability = Literal[
    "available",
    "unavailable",
    "unsupported",
    "installed_import_only",
    "conversion_available",
    "unsupported_without_converter",
]
SourceEvidenceType = Literal[
    "text",
    "table",
    "ocr",
    "cad",
    "coordinate_conversion",
    "groq",
    "user_correction",
]


class DocumentReference(StrictModel):
    document_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    extension: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=1)
    category: DocumentCategory
    document_type: DocumentCategory | None = None
    relevance_score: float = Field(ge=0, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str = Field(min_length=1)
    extractability: Extractability
    priority: DocumentPriority
    purpose: DocumentPurpose
    used_for_design: bool = False
    why_used_or_ignored: str = Field(default="", max_length=1000)
    cad_status: CadStatus = "not_cad"
    duplicate_of: str | None = None
    extraction_status: DocumentExtractionStatus = "not_attempted"
    processing_tools: list[str] = Field(default_factory=list)
    processing_warnings: list[str] = Field(default_factory=list)


class SourceEvidence(StrictModel):
    document_id: str = Field(min_length=1)
    file: str = Field(min_length=1)
    source_type: SourceEvidenceType = "text"
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = None
    layer: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: str = Field(min_length=1, max_length=1000)


class ExtractedField(StrictModel):
    field: str = Field(min_length=1)
    value: str | float | int | bool | list[float] | list[str] | None = None
    status: FieldStatus
    confidence: float = Field(ge=0, le=1)
    sources: list[SourceEvidence] = Field(default_factory=list)
    values: list[str | float | int | bool | list[float] | list[str]] = Field(default_factory=list)
    severity: MissingSeverity | None = None
    resolution: ConflictResolution | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_provenance(self) -> "ExtractedField":
        if self.status == "confirmed" and not self.sources:
            raise ValueError(f"{self.field} is confirmed without source evidence")
        if self.status == "conflict" and len(self.values) < 2:
            raise ValueError(f"{self.field} conflict must include at least two values")
        if self.status == "missing" and not self.severity:
            raise ValueError(f"{self.field} missing value must include severity")
        return self


class RadioSectorDesign(StrictModel):
    sector_id: str = Field(min_length=1)
    azimuth_deg: ExtractedField
    hba_m: ExtractedField
    antenna_model: ExtractedField | None = None
    bands: ExtractedField | None = None
    mechanical_tilt_deg: ExtractedField | None = None
    electrical_tilt_deg: ExtractedField | None = None
    rru: ExtractedField | None = None


class ProjectDesignSpec(StrictModel):
    pack_id: str = Field(min_length=1)
    site_info: dict[str, ExtractedField] = Field(default_factory=dict)
    coordinate_info: dict[str, ExtractedField] = Field(default_factory=dict)
    tower_spec: dict[str, ExtractedField] = Field(default_factory=dict)
    foundation_spec: dict[str, ExtractedField] = Field(default_factory=dict)
    radio_sectors: list[RadioSectorDesign] = Field(default_factory=list)
    antenna_inventory: list[dict[str, ExtractedField]] = Field(default_factory=list)
    rru_inventory: list[dict[str, ExtractedField]] = Field(default_factory=list)
    cabinet_inventory: list[dict[str, ExtractedField]] = Field(default_factory=list)
    cabling_spec: dict[str, ExtractedField] = Field(default_factory=dict)
    grounding_spec: dict[str, ExtractedField] = Field(default_factory=dict)
    compound_spec: dict[str, ExtractedField] = Field(default_factory=dict)
    document_references: list[DocumentReference] = Field(default_factory=list)
    missing_fields: list[ExtractedField] = Field(default_factory=list)
    conflicts: list[ExtractedField] = Field(default_factory=list)
    assumptions: list[ExtractedField] = Field(default_factory=list)
    confidence_summary: dict[str, float | int] = Field(default_factory=dict)
    provenance_map: dict[str, list[SourceEvidence]] = Field(default_factory=dict)
    source_mode: Literal["deterministic", "groq", "mixed"] = "deterministic"
    llm_provider: str | None = None
    llm_fallback_used: bool | None = None
    groq_rejected_fields: list[dict] = Field(default_factory=list)
    processing_capabilities: dict[str, str] = Field(default_factory=dict)
    processing_warnings: list[str] = Field(default_factory=list)


class DocumentPackCorrection(StrictModel):
    field: str = Field(min_length=1)
    value: str | float | int | bool | list[float] | list[str]
    reason: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(default=1.0, ge=0, le=1)
    corrected_by: str = "user"


class DocumentPackSummary(StrictModel):
    pack_id: str = Field(min_length=1)
    status: Literal["indexed", "processed", "failed"]
    document_count: int = Field(ge=0)
    high_priority_count: int = Field(ge=0)
    missing_blocking_count: int = Field(ge=0)
    blocking_fields: list[str] = Field(default_factory=list)
    conflict_count: int = Field(ge=0)
    can_generate_design: bool
    cad_status: dict[str, int] = Field(default_factory=dict)
    qa_score: float | None = Field(default=None, ge=0, le=1)
    correction_count: int = Field(default=0, ge=0)
    processing_warning_count: int = Field(default=0, ge=0)
    tool_status: dict[str, str] = Field(default_factory=dict)
    memory_summary_available: bool = False


class DocumentPackQACheck(StrictModel):
    name: str = Field(min_length=1)
    passed: bool
    reason: str = Field(min_length=1)


class DocumentPackQAReport(StrictModel):
    pack_id: str = Field(min_length=1)
    status: Literal["passed", "warning", "failed"]
    score: float = Field(ge=0, le=1)
    checks: list[DocumentPackQACheck]
    warnings: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    ready_to_generate: bool = False
    ready_confidence: float = Field(default=0.0, ge=0, le=1)
    recommended_user_actions: list[str] = Field(default_factory=list)
    tool_failures: list[str] = Field(default_factory=list)
    memory_writeback: dict = Field(default_factory=dict)


class RequirementMappingResult(StrictModel):
    status: Literal["mapped", "blocked"]
    requirements: dict | None = None
    generated_requirements_text: str | None = None
    blocking_fields: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    network_type: NetworkType | None = None
    mapping_loss_report: dict = Field(default_factory=dict)


class DocumentToolCapability(StrictModel):
    name: str = Field(min_length=1)
    status: ToolAvailability
    purpose: str = Field(min_length=1)
    module: str | None = None
    command: str | None = None
    fallback: str = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)


class DocumentPackCapabilities(StrictModel):
    pdf_text_extraction: DocumentToolCapability
    pdf_table_extraction: DocumentToolCapability
    pdf_layout_extraction: DocumentToolCapability
    ocr: DocumentToolCapability
    dxf_parsing: DocumentToolCapability
    dwg_conversion: DocumentToolCapability
    coordinate_conversion: DocumentToolCapability
    groq_bounded_extraction: DocumentToolCapability

    def status_map(self) -> dict[str, str]:
        return {
            "pdf_text_extraction": self.pdf_text_extraction.status,
            "pdf_table_extraction": self.pdf_table_extraction.status,
            "pdf_layout_extraction": self.pdf_layout_extraction.status,
            "ocr": self.ocr.status,
            "dxf_parsing": self.dxf_parsing.status,
            "dwg_conversion": self.dwg_conversion.status,
            "coordinate_conversion": self.coordinate_conversion.status,
            "groq_bounded_extraction": self.groq_bounded_extraction.status,
        }
