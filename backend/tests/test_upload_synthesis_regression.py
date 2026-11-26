"""Regression tests for automatic document-to-clinical-synthesis workflow."""

import io
import uuid
import pytest
import fitz
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.analysis import AIAnalysis
from app.models.document import Document, ExtractedData


def create_auth_patient_client(custom_name="Regression Patient"):
    """Creates a registered, logged-in patient TestClient."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    email = f"patient_{uid}@example.com"
    reg = c.post(
        "/api/auth/register/patient",
        json={
            "full_name": f"{custom_name} {uid}",
            "email": email,
            "date_of_birth": "1985-06-15",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert reg.status_code == 201
    login_res = c.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123!", "role": "patient"},
    )
    assert login_res.status_code == 200
    c.headers["X-CSRF-Token"] = login_res.json()["csrf_token"]
    me = c.get("/api/auth/me").json()
    patient_id = me["patient_profile"]["id"]
    return c, patient_id


def make_pdf(text: str) -> bytes:
    """Creates a valid PDF binary with text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    b = doc.tobytes()
    doc.close()
    return b


def test_upload_digital_pdf_and_automatic_synthesis_v1():
    """Verify uploading first digital PDF automatically triggers V1 analysis."""
    c, patient_id = create_auth_patient_client()

    pdf_bytes = make_pdf("PRESCRIPTION:\nDiagnosis: Type 2 Diabetes\nMetformin 500mg BID oral")
    files = [("files", ("rx_initial.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]

    res = c.post("/api/documents/upload", files=files, data={"document_type": "prescription"})
    assert res.status_code == 201
    doc_data = res.json()[0]
    assert doc_data["processing_status"] in ["processed", "manual_review"]

    # Verify ExtractedData was saved
    db = SessionLocal()
    ed = db.query(ExtractedData).filter(ExtractedData.document_id == doc_data["id"]).first()
    assert ed is not None
    assert "Metformin" in str(ed.structured_data)

    # Verify that V1 analysis was created automatically without calling /run
    latest = c.get(f"/api/analysis/patients/{patient_id}/latest").json()
    assert latest["version_number"] == 1
    assert latest["status"] == "current"
    assert latest["completeness_score"] > 0
    db.close()


def test_upload_second_pdf_creates_v2_and_marks_v1_outdated():
    """Verify second upload increments to V2 and marks V1 as outdated."""
    c, patient_id = create_auth_patient_client()

    # Upload Doc 1
    pdf1 = make_pdf("PRESCRIPTION 1: Diagnosis: Essential Hypertension. Lisinopril 10mg daily oral.")
    c.post("/api/documents/upload", files=[("files", ("rx1.pdf", io.BytesIO(pdf1), "application/pdf"))])

    v1 = c.get(f"/api/analysis/patients/{patient_id}/latest").json()
    assert v1["version_number"] == 1
    assert v1["status"] == "current"

    # Upload Doc 2: Adds a lab report
    pdf2 = make_pdf("LAB REPORT: Fasting Glucose: 145 mg/dL (Ref 70-99). HbA1c: 8.2% (H)")
    c.post(
        "/api/documents/upload",
        files=[("files", ("labs.pdf", io.BytesIO(pdf2), "application/pdf"))],
        data={"document_type": "lab_report"},
    )

    # Verify V2 is now current
    v2 = c.get(f"/api/analysis/patients/{patient_id}/latest").json()
    assert v2["version_number"] == 2
    assert v2["status"] == "current"

    # Check history in DB: V1 must be preserved as outdated
    db = SessionLocal()
    analyses = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.patient_id == patient_id)
        .order_by(AIAnalysis.version_number.asc())
        .all()
    )
    assert len(analyses) == 2
    assert analyses[0].version_number == 1
    assert analyses[0].status == "outdated"
    assert analyses[1].version_number == 2
    assert analyses[1].status == "current"
    db.close()


def test_batch_upload_creates_single_incremental_version():
    """Ensure a multi-file batch upload triggers exactly one new synthesis version, not N versions."""
    c, patient_id = create_auth_patient_client()

    # First initial doc -> V1
    pdf1 = make_pdf("PRESCRIPTION: Metformin 500mg BID")
    c.post("/api/documents/upload", files=[("files", ("rx1.pdf", io.BytesIO(pdf1), "application/pdf"))])

    # Now upload 2 files in a single batch
    pdf2 = make_pdf("LAB: HbA1c: 7.4% (Ref 4.0-5.6)")
    pdf3 = make_pdf("PRESCRIPTION: Atorvastatin 20mg daily")
    batch_files = [
        ("files", ("labs.pdf", io.BytesIO(pdf2), "application/pdf")),
        ("files", ("rx2.pdf", io.BytesIO(pdf3), "application/pdf")),
    ]
    res_batch = c.post("/api/documents/upload", files=batch_files)
    assert res_batch.status_code == 201
    assert len(res_batch.json()) == 2

    # Should be V2, NOT V3
    db = SessionLocal()
    analyses = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.patient_id == patient_id)
        .order_by(AIAnalysis.version_number.desc())
        .all()
    )
    assert len(analyses) == 2
    assert analyses[0].version_number == 2
    assert analyses[0].status == "current"
    db.close()


def test_document_deletion_updates_synthesis():
    """Verify deleting a document automatically resynthesizes active records."""
    c, patient_id = create_auth_patient_client()

    pdf1 = make_pdf("PRESCRIPTION 1: Metformin 500mg BID")
    res1 = c.post("/api/documents/upload", files=[("files", ("doc1.pdf", io.BytesIO(pdf1), "application/pdf"))])
    doc1_id = res1.json()[0]["id"]

    pdf2 = make_pdf("PRESCRIPTION 2: Lisinopril 20mg daily")
    c.post("/api/documents/upload", files=[("files", ("doc2.pdf", io.BytesIO(pdf2), "application/pdf"))])

    # Deleting doc1 should advance synthesis version to V3
    c.delete(f"/api/documents/{doc1_id}")
    latest = c.get(f"/api/analysis/patients/{patient_id}/latest").json()
    assert latest["version_number"] == 3

    # Active snapshot in database should only contain doc2, not doc1
    db = SessionLocal()
    latest_db = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.patient_id == patient_id)
        .order_by(AIAnalysis.version_number.desc())
        .first()
    )
    assert latest_db.version_number == 3
    assert doc1_id not in (latest_db.document_ids_snapshot or [])
    db.close()


def test_manual_review_and_sparse_document_handling():
    """Verify sparse or handwritten suspect document is safely flagged without crashing synthesis."""
    c, patient_id = create_auth_patient_client()

    # Upload document with almost no text (scanned or sparse)
    sparse_pdf = make_pdf("x")
    res = c.post(
        "/api/documents/upload",
        files=[("files", ("handwritten_rx.pdf", io.BytesIO(sparse_pdf), "application/pdf"))],
        data={"document_type": "prescription"},
    )
    assert res.status_code == 201
    doc_info = res.json()[0]
    assert doc_info["requires_manual_review"] is True
    assert doc_info["processing_status"] == "manual_review"

    # Synthesis should still run without crashing
    latest = c.get(f"/api/analysis/patients/{patient_id}/latest").json()
    assert latest["version_number"] == 1


def test_patient_data_isolation_on_synthesis():
    """Verify Patient B cannot see or trigger Patient A's synthesis or documents."""
    c_a, p_a_id = create_auth_patient_client("Patient A")
    c_b, p_b_id = create_auth_patient_client("Patient B")

    pdf_a = make_pdf("PRESCRIPTION FOR A: Metformin 1000mg BID oral")
    res_a = c_a.post("/api/documents/upload", files=[("files", ("p_a.pdf", io.BytesIO(pdf_a), "application/pdf"))])
    doc_a_id = res_a.json()[0]["id"]

    # Patient B tries to view Patient A's document or extracted facts
    assert c_b.get(f"/api/documents/{doc_a_id}/view").status_code == 403
    assert c_b.get(f"/api/documents/{doc_a_id}/extracted").status_code == 403

    # Patient B tries to fetch Patient A's latest analysis
    assert c_b.get(f"/api/analysis/patients/{p_a_id}/latest").status_code == 403


def test_offline_regex_parser_general_meds_and_labs():
    """Verify that improved offline regex parser extracts general medications and lab tests without inventing diagnoses."""
    c, patient_id = create_auth_patient_client("General Clinical Patient")

    clinical_text = (
        "Encounter Summary\n"
        "Date: 2026-11-20\n"
        "Assessment: Bronchial Asthma\n"
        "Prescriptions:\n"
        "Rx: Atorvastatin 20mg once daily oral\n"
        "Rx: Amoxicillin 500mg three times daily oral\n"
        "Laboratory Evaluation:\n"
        "Serum Creatinine: 1.4 mg/dL (High) (Ref 0.6-1.2)\n"
        "Fasting Plasma Glucose: 135 mg/dL (Ref 70-99)\n"
    )
    pdf_bytes = make_pdf(clinical_text)
    upload_res = c.post(
        "/api/documents/upload",
        files=[("files", ("clinic_encounter.pdf", io.BytesIO(pdf_bytes), "application/pdf"))],
        data={"document_type": "medical_history"},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()[0]["id"]

    # Verify Extracted Data has parsed facts
    ed = c.get(f"/api/documents/{doc_id}/extracted").json()
    struct = ed["structured_data"]
    assert struct["ai_provider"] == "offline_heuristic"
    assert struct["model"] == "clinical_regex_rule_engine"

    # Meds
    med_names = [m["name"] for m in struct["medications"]]
    assert "Atorvastatin" in med_names
    assert "Amoxicillin" in med_names
    ator = next(m for m in struct["medications"] if m["name"] == "Atorvastatin")
    assert "20mg" in ator["dosage"] or "20 mg" in ator["dosage"]

    # Labs
    lab_names = [l["test_name"] for l in struct["lab_results"]]
    assert "Serum Creatinine" in lab_names
    assert "Fasting Plasma Glucose" in lab_names
    creat = next(l for l in struct["lab_results"] if l["test_name"] == "Serum Creatinine")
    assert creat["value"] == "1.4"
    assert creat["is_abnormal"] is True

    # Conditions: Only Asthma was diagnosed; diabetes was NOT diagnosed so should not be in conditions
    cond_names = [c_item["name"] for c_item in struct["conditions"]]
    assert "Bronchial Asthma" in cond_names
    assert "Type 2 Diabetes Mellitus" not in cond_names

    # Check dashboard newest analysis
    latest = c.get(f"/api/analysis/patients/{patient_id}/latest").json()
    assert latest["version_number"] == 1
    assert "Atorvastatin" in latest["summary"]


def test_tesseract_scanned_ocr_fallback_handling():
    """Verify that scanned or image document safely checks Tesseract without unhandled exceptions."""
    from app.document_processing.extractor import DocumentExtractor
    status_info = DocumentExtractor.get_tesseract_status()
    assert isinstance(status_info["available"], bool)
    assert "notice" in status_info
    assert "message" in status_info


def test_realistic_synthetic_pdf_full_lifecycle():
    """
    Tests complete lifecycle with a realistic synthetic PDF containing:
    - Patient identifier
    - Clearly labelled diagnosis
    - Medication name and dosage
    - Two laboratory values with reference ranges
    Verifies: Upload -> Processed -> ExtractedData saved -> V1 -> Second Upload -> V2 -> Dashboard shows V2.
    """
    c, patient_id = create_auth_patient_client("Realistic Synthetic")

    # Upload Doc 1 -> V1
    pdf1 = make_pdf("Patient ID: CLN-PAT-8821\nDiagnosis: Essential Hypertension\nRx: Lisinopril 10mg once daily")
    res1 = c.post(
        "/api/documents/upload",
        files=[("files", ("visit1.pdf", io.BytesIO(pdf1), "application/pdf"))],
        data={"document_type": "prescription"},
    )
    assert res1.status_code == 201
    assert res1.json()[0]["analysis_version"] == 1
    assert res1.json()[0]["synthesis_status"] == "succeeded"

    # Upload Doc 2 (Realistic synthetic PDF with new drug, diagnosis, and 2 labs with ref ranges) -> V2
    realistic_text = (
        "CLINICAL DISCHARGE & LAB SUMMARY\n"
        "Patient Identifier: CLN-PAT-8821\n"
        "Diagnosis: Community-Acquired Pneumonia\n"
        "Medications:\n"
        "Rx: Azithromycin 500mg once daily\n"
        "Laboratory Results:\n"
        "CRP: 45 mg/L (High) (Ref 0.0-10.0)\n"
        "White Blood Cells: 14.2 10^3/uL (High) (Ref 4.5-11.0)\n"
    )
    pdf2 = make_pdf(realistic_text)
    res2 = c.post(
        "/api/documents/upload",
        files=[("files", ("pneumonia_labs.pdf", io.BytesIO(pdf2), "application/pdf"))],
        data={"document_type": "discharge_summary"},
    )
    assert res2.status_code == 201
    doc2_out = res2.json()[0]
    assert doc2_out["processing_status"] == "processed"
    assert doc2_out["analysis_version"] == 2
    assert doc2_out["synthesis_status"] == "succeeded"

    # Verify ExtractedData for Doc 2
    ed2 = c.get(f"/api/documents/{doc2_out['id']}/extracted").json()
    struct2 = ed2["structured_data"]
    assert any(d["name"] == "Community-Acquired Pneumonia" for d in struct2["conditions"])
    assert any(m["name"] == "Azithromycin" and "500mg" in m["dosage"] for m in struct2["medications"])
    lab_names = [l["test_name"] for l in struct2["lab_results"]]
    assert "CRP" in lab_names
    assert "White Blood Cells" in lab_names

    # Verify Latest Analysis on Dashboard API is V2 and reflects new facts
    latest = c.get(f"/api/analysis/patients/{patient_id}/latest").json()
    assert latest["version_number"] == 2
    assert latest["status"] == "current"
    assert "Azithromycin" in latest["summary"]
    assert "Community-Acquired Pneumonia" in latest["summary"]

    # Verify V1 is preserved as outdated
    hist = c.get(f"/api/analysis/patients/{patient_id}/history").json()
    assert len(hist) == 2
    assert hist[0]["version_number"] == 2 and hist[0]["status"] == "current"
    assert hist[1]["version_number"] == 1 and hist[1]["status"] == "outdated"


def test_blank_pdf_marks_failed_and_skips_fake_extraction():
    """Verify a blank PDF with no text/OCR marks processing_status='failed' and never marks Processed."""
    c, patient_id = create_auth_patient_client("Blank Doc Patient")

    # Create a truly empty PDF page
    doc = fitz.open()
    doc.new_page()
    blank_bytes = doc.tobytes()
    doc.close()

    res = c.post(
        "/api/documents/upload",
        files=[("files", ("blank_scan.pdf", io.BytesIO(blank_bytes), "application/pdf"))],
        data={"document_type": "lab_report"},
    )
    assert res.status_code == 201
    doc_out = res.json()[0]
    assert doc_out["processing_status"] == "failed"
    assert doc_out["error_message"] is not None
    assert doc_out["synthesis_status"] == "skipped"
    assert doc_out["analysis_version"] is None

    # ExtractedData must NOT exist
    assert c.get(f"/api/documents/{doc_out['id']}/extracted").status_code == 404


def test_synthesis_failure_reports_error_explicitly(monkeypatch):
    """Verify if synthesis raises an exception, upload returns synthesis_status='failed' with error."""
    c, patient_id = create_auth_patient_client("Synth Fail Patient")

    def boom(*args, **kwargs):
        raise RuntimeError("Simulated synthesis engine failure")

    monkeypatch.setattr("app.routers.documents.execute_patient_analysis", boom)

    pdf = make_pdf("Diagnosis: Asthma\nRx: Albuterol 90mcg inhalation")
    res = c.post(
        "/api/documents/upload",
        files=[("files", ("asthma.pdf", io.BytesIO(pdf), "application/pdf"))],
    )
    assert res.status_code == 201
    doc_out = res.json()[0]
    assert doc_out["processing_status"] == "processed"
    assert doc_out["synthesis_status"] == "failed"
    assert "Simulated synthesis engine failure" in doc_out["synthesis_error"]
    assert doc_out["analysis_version"] is None


def test_tesseract_configured_executable_detected():
    """Verify Tesseract diagnostic helper detects configured/standard executable."""
    from app.document_processing.extractor import DocumentExtractor, configure_tesseract
    import pytesseract

    ok, err = configure_tesseract()
    status_info = DocumentExtractor.get_tesseract_status()
    if ok:
        assert status_info["available"] is True
        assert status_info["tesseract_path"] == pytesseract.pytesseract.tesseract_cmd
        assert "operational" in status_info["message"].lower()
    else:
        assert status_info["available"] is False
        assert err is not None


def test_tesseract_missing_executable_returns_clear_error(monkeypatch):
    """Verify explicit invalid TESSERACT_CMD raises clear validation error."""
    from app.document_processing.extractor import DocumentExtractor

    monkeypatch.setenv("TESSERACT_CMD", r"C:\nonexistent_dir_12345\tesseract.exe")
    status_info = DocumentExtractor.get_tesseract_status()
    assert status_info["available"] is False
    assert "not found" in status_info["error"].lower()

    with pytest.raises(RuntimeError, match="not found"):
        DocumentExtractor.ensure_tesseract_available()


def test_image_ocr_failure_and_real_ocr_upload(monkeypatch):
    """Verify image upload fails cleanly when Tesseract is missing, and succeeds when present."""
    from PIL import Image, ImageDraw
    from app.document_processing.extractor import configure_tesseract

    c, patient_id = create_auth_patient_client("OCR Test Patient")

    img = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 35), "Diagnosis: Asthma\nMetformin 500mg", fill="black")
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_bytes = img_buf.getvalue()

    # 1. Force missing Tesseract -> must fail cleanly without marking Processed
    monkeypatch.setenv("TESSERACT_CMD", r"C:\nonexistent_dir_12345\tesseract.exe")
    res_fail = c.post(
        "/api/documents/upload",
        files=[("files", ("scan_fail.png", io.BytesIO(img_bytes), "image/png"))],
        data={"document_type": "prescription"},
    )
    assert res_fail.status_code == 201
    doc_fail = res_fail.json()[0]
    assert doc_fail["processing_status"] == "failed"
    assert "not found" in doc_fail["error_message"].lower()

    # 2. Restore normal Tesseract detection -> if available on host, image OCR succeeds
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    ok, _ = configure_tesseract()
    if ok:
        res_ok = c.post(
            "/api/documents/upload",
            files=[("files", ("scan_ok.png", io.BytesIO(img_bytes), "image/png"))],
            data={"document_type": "prescription"},
        )
        assert res_ok.status_code == 201
        doc_ok = res_ok.json()[0]
        assert doc_ok["processing_status"] in ["processed", "manual_review"]
        ed = c.get(f"/api/documents/{doc_ok['id']}/extracted").json()
        assert ed["extraction_method"] == "tesseract_ocr"


def test_offline_provider_attribution_never_claims_grok():
    """
    Regression test proving offline-generated analyses and health status
    accurately report 'offline' / 'clinical_rule_engine' and never claim 'grok' or 'grok-3-mini'.
    """
    c, patient_id = create_auth_patient_client("Attribution Patient")

    pdf = make_pdf("Diagnosis: Essential Hypertension\nRx: Lisinopril 10mg once daily")
    res = c.post(
        "/api/documents/upload",
        files=[("files", ("htn.pdf", io.BytesIO(pdf), "application/pdf"))],
        data={"document_type": "prescription"},
    )
    assert res.status_code == 201

    # 1. Latest analysis endpoint
    latest = c.get(f"/api/analysis/patients/{patient_id}/latest").json()
    assert latest["ai_provider"] == "offline"
    assert latest["ai_model"] == "clinical_rule_engine"
    assert "grok" not in latest["ai_provider"].lower()
    assert "grok" not in latest["ai_model"].lower()

    # 2. Analysis history endpoint
    history = c.get(f"/api/analysis/patients/{patient_id}/history").json()
    assert len(history) >= 1
    assert history[0]["ai_provider"] == "offline"
    assert history[0]["ai_model"] == "clinical_rule_engine"

    # 3. Health endpoint when AI_API_KEY is unconfigured
    health = c.get("/api/health").json()
    assert health["ai_provider"] == "offline"

    # 4. DB verification
    db = SessionLocal()
    db_analysis = db.query(AIAnalysis).filter(AIAnalysis.patient_id == patient_id).first()
    assert db_analysis.ai_provider == "offline"
    assert db_analysis.ai_model == "clinical_rule_engine"
    db.close()




