"""Document management router: upload, list, categorize, view, retry, and delete."""

import os
import shutil
from pathlib import Path
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.document import Document, ExtractedData
from app.schemas.document import (
    DocumentOut,
    DocumentUpdateCategoryRequest,
    ExtractedDataOut,
)
from app.utils.dependencies import get_current_user, require_patient
from app.document_processing.extractor import DocumentExtractor
from app.ai.provider_factory import AIProviderFactory

router = APIRouter(prefix="/documents", tags=["Documents"])

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
}


async def process_document_pipeline(document: Document, db: Session):
    """Executes the extraction and AI structured analysis pipeline."""
    document.processing_status = "processing"
    document.error_message = None
    db.commit()

    try:
        # Step 1: Extract Text & Page References
        extracted = DocumentExtractor.extract_from_file(
            file_path=document.storage_path,
            mime_type=document.mime_type,
            filename=document.filename,
        )

        # Step 2: AI Clinical Information Extraction
        ai_provider = AIProviderFactory.get_provider()
        ai_result = await ai_provider.extract_clinical_data(
            filename=document.filename,
            document_type=document.document_type,
            page_texts=extracted["page_texts"],
        )

        # If heuristic or AI detected handwritten / low confidence
        needs_review = extracted["requires_manual_review"] or ai_result.requires_manual_review
        document.requires_manual_review = needs_review
        document.processing_status = "manual_review" if needs_review else "processed"

        # Update or create ExtractedData record
        existing_data = db.query(ExtractedData).filter(ExtractedData.document_id == document.id).first()
        if existing_data:
            existing_data.raw_text = extracted["raw_text"]
            existing_data.page_count = extracted["page_count"]
            existing_data.page_texts = extracted["page_texts"]
            existing_data.structured_data = ai_result.model_dump()
            existing_data.extraction_method = extracted["method"]
        else:
            new_data = ExtractedData(
                document_id=document.id,
                raw_text=extracted["raw_text"],
                page_count=extracted["page_count"],
                page_texts=extracted["page_texts"],
                structured_data=ai_result.model_dump(),
                extraction_method=extracted["method"],
            )
            db.add(new_data)

        db.commit()
    except Exception as e:
        document.processing_status = "failed"
        document.error_message = str(e)
        db.commit()


@router.post("/upload", response_model=list[DocumentOut], status_code=status.HTTP_201_CREATED)
async def upload_documents(
    files: list[UploadFile] = File(...),
    document_type: str = Form("other"),
    user: User = Depends(require_patient),
    db: Session = Depends(get_db),
):
    """Upload one or more medical documents, validate, store privately, and run extraction."""
    patient = user.patient_profile
    if not patient:
        raise HTTPException(status_code=400, detail="User is not a registered patient.")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload.")

    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    upload_dir = settings.resolved_upload_dir / f"patient_{patient.id}"
    upload_dir.mkdir(parents=True, exist_ok=True)

    created_docs = []

    for file in files:
        if not file.filename:
            continue

        ext = Path(file.filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format '{ext}' for '{file.filename}'. Allowed: PDF, PNG, JPG, JPEG.",
            )

        # Generate unique storage filename
        stored_name = f"doc_{os.urandom(8).hex()}{ext}"
        storage_dest = upload_dir / stored_name

        # Read into memory/spool to check size
        contents = await file.read()
        file_size = len(contents)
        if file_size > max_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit.",
            )

        with open(storage_dest, "wb") as f_out:
            f_out.write(contents)

        mime = file.content_type or "application/octet-stream"
        if ext == ".pdf":
            mime = "application/pdf"
        elif ext == ".png":
            mime = "image/png"
        elif ext in [".jpg", ".jpeg"]:
            mime = "image/jpeg"

        doc = Document(
            patient_id=patient.id,
            filename=file.filename,
            stored_filename=stored_name,
            storage_path=str(storage_dest),
            document_type=document_type if document_type in [
                "prescription", "lab_report", "discharge_summary", "medical_history", "other"
            ] else "other",
            mime_type=mime,
            file_size_bytes=file_size,
            processing_status="uploaded",
        )
        db.add(doc)
        db.flush()

        # Run pipeline
        await process_document_pipeline(doc, db)
        created_docs.append(doc)

    return created_docs


@router.get("", response_model=list[DocumentOut])
def list_documents(
    category: str | None = None,
    status: str | None = None,
    user: User = Depends(require_patient),
    db: Session = Depends(get_db),
):
    """List documents belonging to the authenticated patient with optional filtering."""
    patient = user.patient_profile
    query = db.query(Document).filter(
        Document.patient_id == patient.id,
        Document.is_deleted == False,
    )
    if category:
        query = query.filter(Document.document_type == category)
    if status:
        query = query.filter(Document.processing_status == status)

    return query.order_by(Document.uploaded_at.desc()).all()


@router.get("/{document_id}/view")
def view_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Safely stream the private document file to authorized users."""
    doc = db.query(Document).filter(Document.id == document_id, Document.is_deleted == False).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Authorization guard: owner patient, or authorized doctor
    if user.role == "patient":
        if not user.patient_profile or doc.patient_id != user.patient_profile.id:
            raise HTTPException(status_code=403, detail="Unauthorized access to this document.")
    elif user.role != "doctor":
        raise HTTPException(status_code=403, detail="Unauthorized access.")

    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Underlying document file not found.")

    return FileResponse(
        path=str(path),
        media_type=doc.mime_type,
        filename=doc.filename,
    )


@router.get("/{document_id}/extracted", response_model=ExtractedDataOut)
def get_extracted_document_data(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve raw and structured AI extraction data for a document."""
    doc = db.query(Document).filter(Document.id == document_id, Document.is_deleted == False).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if user.role == "patient":
        if not user.patient_profile or doc.patient_id != user.patient_profile.id:
            raise HTTPException(status_code=403, detail="Unauthorized access.")

    extracted = db.query(ExtractedData).filter(ExtractedData.document_id == document_id).first()
    if not extracted:
        raise HTTPException(status_code=404, detail="No extraction data available for this document.")

    return extracted


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document_category(
    document_id: int,
    payload: DocumentUpdateCategoryRequest,
    user: User = Depends(require_patient),
    db: Session = Depends(get_db),
):
    """Allows a patient to update the categorization of their document."""
    patient = user.patient_profile
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.patient_id == patient.id,
        Document.is_deleted == False,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc.document_type = payload.document_type
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/{document_id}/retry", response_model=DocumentOut)
async def retry_document_processing(
    document_id: int,
    user: User = Depends(require_patient),
    db: Session = Depends(get_db),
):
    """Retries text extraction and AI analysis pipeline for a document."""
    patient = user.patient_profile
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.patient_id == patient.id,
        Document.is_deleted == False,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    await process_document_pipeline(doc, db)
    db.refresh(doc)
    return doc


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    user: User = Depends(require_patient),
    db: Session = Depends(get_db),
):
    """Soft-deletes a document, preserving audit integrity while removing from active list."""
    patient = user.patient_profile
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.patient_id == patient.id,
        Document.is_deleted == False,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc.is_deleted = True
    db.commit()
    return {"status": "success", "message": f"Document '{doc.filename}' deleted successfully."}
