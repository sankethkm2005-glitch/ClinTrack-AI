"""SQLAlchemy models for Users, Patient Profiles, and Doctor Profiles."""

from datetime import datetime, date, timezone
from sqlalchemy import Integer, String, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.database import Base


class User(Base):
    """User account entity for both patients and doctors."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # "patient" or "doctor"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    patient_profile: Mapped["PatientProfile | None"] = relationship(
        "PatientProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    doctor_profile: Mapped["DoctorProfile | None"] = relationship(
        "DoctorProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class PatientProfile(Base):
    """Profile data for registered patients."""
    __tablename__ = "patient_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="patient_profile")


class DoctorProfile(Base):
    """Profile and provisional verification details for registered doctors."""
    __tablename__ = "doctor_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    medical_council: Mapped[str] = mapped_column(String(255), nullable=False)
    specialization: Mapped[str] = mapped_column(String(255), nullable=False)
    certificate_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    certificate_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, provisional, verified, rejected
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="doctor_profile")
