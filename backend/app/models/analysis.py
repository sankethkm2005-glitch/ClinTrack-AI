"""SQLAlchemy models for versioned AI analyses and clinical findings."""

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.database import Base


class AIAnalysis(Base):
    """Stores versioned AI clinical intelligence analyses for a patient."""
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(50), default="current", nullable=False, index=True
    )  # current, outdated, failed
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    completeness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completeness_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timeline: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ai_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_model: Mapped[str] = mapped_column(String(100), nullable=False)
    document_ids_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", backref="analyses")
    findings: Mapped[list["AIFinding"]] = relationship(
        "AIFinding", back_populates="analysis", cascade="all, delete-orphan"
    )


class AIFinding(Base):
    """Clinical findings: medication discrepancy, contradiction, lab abnormality, missing info."""
    __tablename__ = "ai_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    analysis_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # medication, contradiction, lab, missing_information, timeline
    priority: Mapped[str] = mapped_column(
        String(50), default="needs_review", nullable=False
    )  # critical, needs_review, informational
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, reviewed, clarification_requested, resolved
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    analysis: Mapped["AIAnalysis"] = relationship("AIAnalysis", back_populates="findings")
