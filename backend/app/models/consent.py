"""SQLAlchemy models for Consent, Doctor Reviews, Notifications, and Audit Logs."""

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.database import Base


class AccessRequest(Base):
    """Doctor's request to access a patient's medical records."""
    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )  # pending, approved, rejected, expired
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    doctor: Mapped["User"] = relationship("User", foreign_keys=[doctor_id])
    patient: Mapped["PatientProfile"] = relationship("PatientProfile", foreign_keys=[patient_id])
    grant: Mapped["AccessGrant | None"] = relationship("AccessGrant", back_populates="request", uselist=False)


class AccessGrant(Base):
    """Approved, scoped, time-limited access grant for a doctor."""
    __tablename__ = "access_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("access_requests.id", ondelete="SET NULL"), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(100), default="full_records", nullable=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    doctor: Mapped["User"] = relationship("User", foreign_keys=[doctor_id])
    patient: Mapped["PatientProfile"] = relationship("PatientProfile", foreign_keys=[patient_id])
    request: Mapped["AccessRequest | None"] = relationship("AccessRequest", back_populates="grant")


class FindingReview(Base):
    """Doctor's clinical review of an AI finding stored separately from the finding."""
    __tablename__ = "finding_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    finding_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_findings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # accept, reject, clarification, resolve
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    finding: Mapped["AIFinding"] = relationship("AIFinding", backref="reviews")
    doctor: Mapped["User"] = relationship("User", foreign_keys=[doctor_id])


class Notification(Base):
    """In-app notifications for patients and doctors."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notification_type: Mapped[str] = mapped_column(
        String(50), default="consent", nullable=False
    )  # consent, emergency, review, system
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class AuditLog(Base):
    """Immutable audit trail for security, consent, and record access events."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])
