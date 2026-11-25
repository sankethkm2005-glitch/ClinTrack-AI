"""Automated tests for Phase 5 Clinical Intelligence Engine, Timeline, and Versioning."""

import io
import uuid
import pytest
import fitz
from fastapi.testclient import TestClient

from app.main import app


def create_sample_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_patient_with_records():
    """Helper creating a patient with multi-document records demonstrating reconciliation."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    email = f"intel_p_{uid}@example.com"
    c.post(
        "/api/auth/register/patient",
        json={
            "full_name": f"Clinical Intel Patient {uid}",
            "email": email,
            "date_of_birth": "1980-04-12",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    login_res = c.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123!", "role": "patient"},
    )
    c.headers["X-CSRF-Token"] = login_res.json()["csrf_token"]
    pat_id = c.get("/api/patients/me").json()["id"]

    # Upload Doc 1: Prescription with Metformin 500mg and Diabetes
    pdf1 = create_sample_pdf("PRESCRIPTION: Type 2 Diabetes. Metformin 500mg BID oral.")
    c.post(
        "/api/documents/upload",
        files=[("files", ("rx1.pdf", io.BytesIO(pdf1), "application/pdf"))],
        data={"document_type": "prescription"},
    )

    # Upload Doc 2: Prescription with conflicting Metformin 1000mg
    pdf2 = create_sample_pdf("PRESCRIPTION 2: Metformin 1000mg BID oral. Lisinopril 10mg daily.")
    c.post(
        "/api/documents/upload",
        files=[("files", ("rx2.pdf", io.BytesIO(pdf2), "application/pdf"))],
        data={"document_type": "prescription"},
    )

    # Upload Doc 3: Lab report with abnormal HbA1c
    pdf3 = create_sample_pdf("LAB REPORT: HbA1c: 7.8% (H) (Ref 4.0-5.6)")
    c.post(
        "/api/documents/upload",
        files=[("files", ("labs.pdf", io.BytesIO(pdf3), "application/pdf"))],
        data={"document_type": "lab_report"},
    )

    return c, pat_id


def test_clinical_reconstruction_and_versioning():
    """Verify run_patient_analysis produces V1, timeline, findings, and completeness score."""
    c, pat_id = create_patient_with_records()

    # Run Analysis V1
    res = c.post(f"/api/analysis/patients/{pat_id}/run")
    assert res.status_code == 200
    data = res.json()
    assert data["version_number"] == 1
    assert data["status"] == "current"
    assert data["completeness_score"] > 0
    assert len(data["timeline"]) >= 2
    assert "findings" in data
    assert any(f["finding_type"] == "medication" for f in data["findings"])
    assert any(f["finding_type"] == "lab" for f in data["findings"])

    # Run Analysis V2
    res2 = c.post(f"/api/analysis/patients/{pat_id}/run")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["version_number"] == 2
    assert data2["status"] == "current"

    # Verify history retains V1 (marked outdated) and V2 (marked current)
    hist_res = c.get(f"/api/analysis/patients/{pat_id}/history")
    assert hist_res.status_code == 200
    versions = hist_res.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[0]["status"] == "current"
    assert versions[1]["version_number"] == 1
    assert versions[1]["status"] == "outdated"


def test_medication_discrepancy_detection():
    """Verify medication reconciliation identifies conflicting dosages across documents."""
    c, pat_id = create_patient_with_records()
    res = c.post(f"/api/analysis/patients/{pat_id}/run")
    findings = res.json()["findings"]

    med_findings = [f for f in findings if f["finding_type"] == "medication"]
    assert len(med_findings) >= 1
    disc = med_findings[0]
    assert "Discrepancy" in disc["title"] or "Variation" in disc["title"]
    assert len(disc["evidence"]) >= 2
    assert disc["evidence"][0]["document_name"] != ""


def test_lab_analysis_abnormality():
    """Verify laboratory findings flag abnormal values."""
    c, pat_id = create_patient_with_records()
    res = c.post(f"/api/analysis/patients/{pat_id}/run")
    findings = res.json()["findings"]

    lab_findings = [f for f in findings if f["finding_type"] == "lab"]
    assert len(lab_findings) >= 1
    hba1c_f = lab_findings[0]
    assert "HbA1c" in hba1c_f["title"]
    assert hba1c_f["priority"] in ["critical", "needs_review"]


def test_timeline_evidence_links():
    """Verify every event in the timeline retains source document and page number."""
    c, pat_id = create_patient_with_records()
    res = c.post(f"/api/analysis/patients/{pat_id}/run")
    timeline = res.json()["timeline"]

    assert len(timeline) >= 2
    for event in timeline:
        assert event["document_id"] is not None
        assert event["document_name"] != ""
        assert event["page_number"] >= 1


def test_patient_isolation_analysis():
    """Verify Patient B cannot run or view Patient A's analysis."""
    c_a, pat_a_id = create_patient_with_records()
    c_b, pat_b_id = create_patient_with_records()

    # Patient B tries to run analysis on Patient A
    unauth_run = c_b.post(f"/api/analysis/patients/{pat_a_id}/run")
    assert unauth_run.status_code == 403

    # Patient B tries to view latest analysis of Patient A
    unauth_get = c_b.get(f"/api/analysis/patients/{pat_a_id}/latest")
    assert unauth_get.status_code == 403


def test_clinical_report_pdf_generation():
    """Verify downloadable PDF clinical report generation with valid PDF magic header."""
    import fitz
    c, pat_id = create_patient_with_records()
    # First run analysis
    c.post(f"/api/analysis/patients/{pat_id}/run")

    # Request PDF report
    res = c.get(f"/api/analysis/patients/{pat_id}/report.pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    
    # Verify PDF content renders correctly using PyMuPDF parser
    doc = fitz.open(stream=res.content, filetype="pdf")
    assert len(doc) >= 1
    extracted_text = "".join(page.get_text() for page in doc)
    assert "ClinTrace AI" in extracted_text
    assert "decision-support prototype" in extracted_text.lower()
    assert "PATIENT IDENTIFICATION" in extracted_text


def test_lab_trend_analysis_endpoint():
    """Verify lab trend endpoint groups compatible lab tests and chronological values."""
    c, pat_id = create_patient_with_records()
    # Run analysis to populate structured lab results
    c.post(f"/api/analysis/patients/{pat_id}/run")

    res = c.get(f"/api/analysis/patients/{pat_id}/lab-trends")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    # Check HbA1c test entry
    hba1c = next((t for t in data if "HbA1c" in t["test_name"]), None)
    assert hba1c is not None
    assert hba1c["unit"] == "%"
    assert len(hba1c["data_points"]) >= 1
    point = hba1c["data_points"][0]
    assert point["value"] == 7.8
    assert point["is_abnormal"] is True


def test_tesseract_diagnostic_status():
    """Verify Tesseract OCR diagnostic helper returns structured detection status."""
    from app.document_processing.extractor import DocumentExtractor
    status_info = DocumentExtractor.get_tesseract_status()
    assert "available" in status_info
    assert isinstance(status_info["available"], bool)
    assert "message" in status_info
    assert "tesseract_path" in status_info

