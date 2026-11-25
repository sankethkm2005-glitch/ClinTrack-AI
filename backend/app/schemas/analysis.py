"""Pydantic schemas for versioned AI analyses and clinical findings."""

from datetime import datetime
from pydantic import BaseModel, Field


class AIFindingOut(BaseModel):
    id: int
    analysis_id: int
    finding_type: str
    priority: str
    title: str
    description: str
    evidence: list[dict] | dict | None = None
    review_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TimelineEvent(BaseModel):
    date: str | None = None
    event_type: str
    title: str
    description: str | None = None
    document_id: int | None = None
    document_name: str | None = None
    page_number: int | None = 1
    evidence_text: str | None = None


class AIAnalysisOut(BaseModel):
    id: int
    patient_id: int
    version_number: int
    status: str
    summary: str
    completeness_score: int
    completeness_breakdown: dict | None = None
    timeline: list[TimelineEvent] | None = None
    ai_provider: str
    ai_model: str
    created_at: datetime
    findings: list[AIFindingOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AIAnalysisHistoryItem(BaseModel):
    id: int
    version_number: int
    status: str
    completeness_score: int
    summary: str
    created_at: datetime

    model_config = {"from_attributes": True}
