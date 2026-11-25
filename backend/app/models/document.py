"""SQLAlchemy models for medical documents and extracted clinical data."""

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.database import Base


class Document(Base):
    """Uploaded medical document entity stored privately."""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(50), default="other", nullable=False
    )  # prescription, lab_report, discharge_summary, medical_history, other
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_status: Mapped[str] = mapped_column(
        String(50), default="uploaded", nullable=False, index=True
    )  # uploaded, processing, processed, manual_review, failed
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    patient: Mapped["PatientProfile"] = relationship("PatientProfile", backref="documents")
    extracted_data: Mapped["ExtractedData | None"] = relationship(
        "ExtractedData", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )


class ExtractedData(Base):
    """Raw text and structured clinical information extracted from a document."""
    __tablename__ = "extracted_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    page_texts: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    structured_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extraction_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # pdf_text, tesseract_ocr, manual_fallback
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    document: Mapped["Document"] = relationship("Document", back_populates="extracted_data")
