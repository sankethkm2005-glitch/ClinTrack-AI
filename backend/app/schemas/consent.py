"""Pydantic schemas for consent requests, grants, reviews, notifications, and audits."""

from datetime import datetime
from pydantic import BaseModel, Field


class AccessRequestCreate(BaseModel):
    patient_id_str: str = Field(..., description="Unique patient identifier, e.g. CLN-PAT-1001")
    reason: str = Field(..., min_length=5, max_length=1000)


class EmergencyAccessCreate(BaseModel):
    patient_id_str: str = Field(..., description="Unique patient identifier")
    reason: str = Field(..., min_length=10, max_length=1000, description="Mandatory clinical emergency justification")


class AccessRequestAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    duration_hours: int = Field(default=24, ge=1, le=720)


class AccessRequestOut(BaseModel):
    id: int
    doctor_id: int
    doctor_name: str | None = None
    doctor_specialization: str | None = None
    patient_id: int
    patient_id_str: str | None = None
    patient_name: str | None = None
    reason: str
    is_emergency: bool
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AccessGrantOut(BaseModel):
    id: int
    doctor_id: int
    doctor_name: str | None = None
    patient_id: int
    patient_id_str: str | None = None
    patient_name: str | None = None
    scope: str
    is_emergency: bool
    is_active: bool = True
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FindingReviewCreate(BaseModel):
    action: str = Field(..., pattern="^(accept|reject|clarification|resolve)$")
    explanation: str = Field(..., min_length=3, max_length=2000)


class FindingReviewOut(BaseModel):
    id: int
    finding_id: int
    doctor_id: int
    doctor_name: str | None = None
    action: str
    explanation: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationOut(BaseModel):
    id: int
    title: str
    message: str
    notification_type: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: int
    user_id: int | None = None
    action: str
    resource_type: str
    resource_id: str
    details: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
