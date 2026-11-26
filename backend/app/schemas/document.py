"""Pydantic schemas for medical document management and clinical extraction."""

from datetime import datetime
from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: int
    patient_id: int
    filename: str
    stored_filename: str
    document_type: str
    mime_type: str
    file_size_bytes: int
    processing_status: str
    requires_manual_review: bool
    error_message: str | None = None
    uploaded_at: datetime
    analysis_version: int | None = None
    synthesis_status: str | None = None
    synthesis_error: str | None = None

    model_config = {"from_attributes": True}


class DocumentUpdateCategoryRequest(BaseModel):
    document_type: str = Field(
        ...,
        pattern="^(prescription|lab_report|discharge_summary|medical_history|other)$",
    )


class ClinicalCondition(BaseModel):
    name: str
    status: str | None = None  # active, historical, suspected
    onset_date: str | None = None
    page_number: int | None = 1
    evidence_text: str | None = None


class Medication(BaseModel):
    name: str
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None
    start_date: str | None = None
    status: str | None = None  # active, discontinued, unknown
    page_number: int | None = 1
    evidence_text: str | None = None


class LabResult(BaseModel):
    test_name: str
    value: str
    unit: str | None = None
    reference_range: str | None = None
    is_abnormal: bool | None = None
    test_date: str | None = None
    page_number: int | None = 1
    evidence_text: str | None = None


class ClinicalExtractionResult(BaseModel):
    document_type: str = "other"
    patient_name: str | None = None
    patient_dob: str | None = None
    conditions: list[ClinicalCondition] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    lab_results: list[LabResult] = Field(default_factory=list)
    clinical_notes: list[str] = Field(default_factory=list)
    requires_manual_review: bool = False
    review_reason: str | None = None
    extracted_summary: str | None = None
    ai_provider: str = "none"
    model: str = "none"


class ExtractedDataOut(BaseModel):
    id: int
    document_id: int
    raw_text: str
    page_count: int
    page_texts: list[dict] | None = None
    structured_data: ClinicalExtractionResult | None = None
    extraction_method: str
    created_at: datetime

    model_config = {"from_attributes": True}
