"""Automated tests for Phase 3 (Document Management) and Phase 4 (AI Integration Pipeline)."""

import io
import uuid
import pytest
import fitz  # PyMuPDF
from fastapi.testclient import TestClient

from app.main import app


def create_sample_pdf(text: str) -> bytes:
    """Helper to create an in-memory test PDF with provided text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_auth_client(role: str = "patient"):
    """Helper returning an authenticated TestClient with CSRF header preconfigured."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    email = f"user_{uid}@example.com"

    if role == "patient":
        c.post(
            "/api/auth/register/patient",
            json={
                "full_name": f"Patient {uid}",
                "email": email,
                "date_of_birth": "1988-11-20",
                "password": "Password123!",
                "confirm_password": "Password123!",
            },
        )
    else:
        c.post(
            "/api/auth/register/doctor",
            data={
                "full_name": f"Dr. {uid}",
                "email": email,
                "password": "DoctorPassword123!",
                "confirm_password": "DoctorPassword123!",
                "registration_number": f"REG-{uid}",
                "medical_council": "Medical Council",
                "specialization": "Cardiology",
            },
        )

    login_res = c.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123!" if role == "patient" else "DoctorPassword123!", "role": role},
    )
    csrf_token = login_res.json()["csrf_token"]
    c.headers["X-CSRF-Token"] = csrf_token
    return c


@pytest.fixture
def auth_patient():
    return create_auth_client("patient")


@pytest.fixture
def auth_other_patient():
    return create_auth_client("patient")


def test_upload_document_success(auth_patient):
    """Verify patient can upload a medical PDF and triggering extraction pipeline."""
    pdf_content = create_sample_pdf(
        "CLINICAL VISIT SUMMARY\nPatient: John Doe\nDiagnosis: Essential Hypertension\nRx: Lisinopril 10mg daily oral"
    )
    files = [("files", ("visit_summary.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    data = {"document_type": "discharge_summary"}

    res = auth_patient.post("/api/documents/upload", files=files, data=data)
    assert res.status_code == 201
    docs = res.json()
    assert len(docs) == 1
    doc = docs[0]
    assert doc["filename"] == "visit_summary.pdf"
    assert doc["document_type"] == "discharge_summary"
    assert doc["processing_status"] in ["processed", "manual_review"]


def test_upload_invalid_file_format_rejected(auth_patient):
    """Ensure unsupported file extensions are rejected with 400 Bad Request."""
    files = [("files", ("malicious.exe", io.BytesIO(b"fake binary"), "application/octet-stream"))]
    res = auth_patient.post("/api/documents/upload", files=files)
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]


def test_list_documents_filtering(auth_patient):
    """Verify document listing by category and processing status."""
    pdf_content = create_sample_pdf("Discharge notes")
    files = [("files", ("discharge.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    auth_patient.post("/api/documents/upload", files=files, data={"document_type": "discharge_summary"})

    res = auth_patient.get("/api/documents?category=discharge_summary")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) >= 1
    for d in docs:
        assert d["document_type"] == "discharge_summary"


def test_document_patient_isolation(auth_patient, auth_other_patient):
    """Ensure Patient A cannot view or access documents uploaded by Patient B."""
    pdf_content = create_sample_pdf("Private records for Patient A")
    files = [("files", ("private_record.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    upload_res = auth_patient.post("/api/documents/upload", files=files)
    doc_id = upload_res.json()[0]["id"]

    # Patient B attempts to view Patient A's document
    unauth_view = auth_other_patient.get(f"/api/documents/{doc_id}/view")
    assert unauth_view.status_code == 403
    assert "Unauthorized" in unauth_view.json()["detail"]

    # Patient B attempts to delete Patient A's document
    unauth_del = auth_other_patient.delete(f"/api/documents/{doc_id}")
    assert unauth_del.status_code == 404  # Not found under Patient B's records


def test_update_document_category(auth_patient):
    """Verify patient can change category of their document."""
    pdf_content = create_sample_pdf("Lab results: HbA1c 7.2%")
    files = [("files", ("lab.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    upload_res = auth_patient.post("/api/documents/upload", files=files, data={"document_type": "other"})
    doc_id = upload_res.json()[0]["id"]

    patch_res = auth_patient.patch(
        f"/api/documents/{doc_id}",
        json={"document_type": "lab_report"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["document_type"] == "lab_report"


def test_extracted_clinical_facts_available(auth_patient):
    """Verify that structured clinical information and page references are extracted."""
    pdf_content = create_sample_pdf(
        "CLINICAL NOTE\nDiagnosis: Type 2 Diabetes\nMedication: Metformin 500mg BID\nLab: HbA1c 7.8%"
    )
    files = [("files", ("diabetes_check.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    upload_res = auth_patient.post("/api/documents/upload", files=files, data={"document_type": "prescription"})
    doc_id = upload_res.json()[0]["id"]

    extracted_res = auth_patient.get(f"/api/documents/{doc_id}/extracted")
    assert extracted_res.status_code == 200
    extracted = extracted_res.json()
    assert extracted["document_id"] == doc_id
    assert extracted["raw_text"] != ""
    assert extracted["page_count"] == 1
    assert "structured_data" in extracted


def test_handwritten_flagged_for_manual_review(auth_patient):
    """Verify handwritten prescriptions are flagged as manual review required."""
    pdf_content = create_sample_pdf("Dr handwriting Rx illegible scribble")
    files = [("files", ("rx_handwritten_sample.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    upload_res = auth_patient.post("/api/documents/upload", files=files, data={"document_type": "prescription"})
    doc = upload_res.json()[0]
    assert doc["requires_manual_review"] is True
    assert doc["processing_status"] == "manual_review"


def test_retry_document_processing(auth_patient):
    """Verify retry endpoint re-processes the document."""
    pdf_content = create_sample_pdf("Retry document test")
    files = [("files", ("retry_doc.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    upload_res = auth_patient.post("/api/documents/upload", files=files)
    doc_id = upload_res.json()[0]["id"]

    retry_res = auth_patient.post(f"/api/documents/{doc_id}/retry")
    assert retry_res.status_code == 200
    assert retry_res.json()["id"] == doc_id


def test_delete_document_soft_delete(auth_patient):
    """Verify deleting document marks it deleted and hides it from document list."""
    pdf_content = create_sample_pdf("To be deleted")
    files = [("files", ("delete_me.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    upload_res = auth_patient.post("/api/documents/upload", files=files)
    doc_id = upload_res.json()[0]["id"]

    del_res = auth_patient.delete(f"/api/documents/{doc_id}")
    assert del_res.status_code == 200

    # Ensure it no longer appears in active list
    list_res = auth_patient.get("/api/documents")
    doc_ids = [d["id"] for d in list_res.json()]
    assert doc_id not in doc_ids
