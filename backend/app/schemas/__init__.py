"""Auth schemas export."""

from app.schemas.auth import (
    PatientRegisterRequest,
    DoctorRegisterRequest,
    LoginRequest,
    UserOut,
    PatientProfileOut,
    DoctorProfileOut,
)

__all__ = [
    "PatientRegisterRequest",
    "DoctorRegisterRequest",
    "LoginRequest",
    "UserOut",
    "PatientProfileOut",
    "DoctorProfileOut",
]
