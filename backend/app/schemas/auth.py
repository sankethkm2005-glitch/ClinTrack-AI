"""Pydantic schemas for authentication and profiles."""

from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class PatientRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    date_of_birth: date
    gender: str | None = Field(default=None, max_length=50)


class DoctorRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    registration_number: str = Field(..., min_length=2, max_length=100)
    medical_council: str = Field(..., min_length=2, max_length=255)
    specialization: str = Field(..., min_length=2, max_length=255)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str
    role: str = Field(..., pattern="^(patient|doctor)$")


class PatientProfileOut(BaseModel):
    id: int
    patient_id: str
    full_name: str
    date_of_birth: date
    gender: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DoctorProfileOut(BaseModel):
    id: int
    full_name: str
    registration_number: str
    medical_council: str
    specialization: str
    certificate_path: str | None = None
    verification_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime
    patient_profile: PatientProfileOut | None = None
    doctor_profile: DoctorProfileOut | None = None

    model_config = {"from_attributes": True}
