"""End-to-End integration test covering the entire ClinTrace AI clinical lifecycle."""

import io
import uuid
import pytest
import fitz
from fastapi.testclient import TestClient
from app.main import app


def test_full_clinical_workflow_end_to_end():
    """
    Simulates complete hackathon demo workflow:
    1. Patient registration & login.
    2. Document upload (PDF visit note & lab report).
    3. Clinical intelligence synthesis & versioning (V1).
    4. Doctor registration & login.
    5. Doctor patient search & access request.
    6. Patient approval creating scoped time-limited grant.
    7. Doctor opens 3-panel clinical workspace.
    8. Doctor reviews an AI discrepancy finding.
    9. Patient verifies notification and revokes grant.
    10. Doctor is subsequently blocked from workspace.
    """
    uid = uuid.uuid4().hex[:6]
    p_client = TestClient(app)
    d_client = TestClient(app)

    # 1. Patient Registration
    p_email = f"e2e_pat_{uid}@example.com"
    p_reg = p_client.post(
        "/api/auth/register/patient",
        json={
            "full_name": f"E2E Patient {uid}",
            "email": p_email,
            "date_of_birth": "1983-07-22",
            "gender": "Female",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert p_reg.status_code == 201
    pat_str = p_reg.json()["patient_profile"]["patient_id"]
    pat_id = p_reg.json()["patient_profile"]["id"]

    # Patient Login
    p_log = p_client.post("/api/auth/login", json={"email": p_email, "password": "Password123!", "role": "patient"})
    assert p_log.status_code == 200
    p_client.headers["X-CSRF-Token"] = p_log.json()["csrf_token"]

    # 2. Upload Medical Documents
    doc1_pdf = fitz.open()
    p1 = doc1_pdf.new_page()
    p1.insert_text((50, 72), "DISCHARGE SUMMARY: Type 2 Diabetes Mellitus. Metformin 500mg BID oral.")
    b1 = doc1_pdf.tobytes()
    doc1_pdf.close()

    doc2_pdf = fitz.open()
    p2 = doc2_pdf.new_page()
    p2.insert_text((50, 72), "LABORATORY PANEL: HbA1c: 7.9% (H) (Reference: 4.0 - 5.6)")
    b2 = doc2_pdf.tobytes()
    doc2_pdf.close()

    up_res = p_client.post(
        "/api/documents/upload",
        files=[
            ("files", ("discharge.pdf", io.BytesIO(b1), "application/pdf")),
            ("files", ("lab_results.pdf", io.BytesIO(b2), "application/pdf")),
        ],
        data={"document_type": "discharge_summary"},
    )
    assert up_res.status_code == 201
    assert len(up_res.json()) == 2

    # 3. Clinical Intelligence Run (Automatically generated V1 upon upload)
    run_res = p_client.get(f"/api/analysis/patients/{pat_id}/latest")
    assert run_res.status_code == 200
    analysis_data = run_res.json()
    assert analysis_data["version_number"] == 1
    assert len(analysis_data["timeline"]) >= 1
    assert len(analysis_data["findings"]) >= 1
    target_finding_id = analysis_data["findings"][0]["id"]

    # 4. Doctor Registration & Login
    d_email = f"e2e_doc_{uid}@hospital.org"
    d_reg = d_client.post(
        "/api/auth/register/doctor",
        data={
            "full_name": f"Dr. E2E Clinician {uid}",
            "email": d_email,
            "password": "DoctorPassword123!",
            "confirm_password": "DoctorPassword123!",
            "registration_number": f"REG-E2E-{uid}",
            "medical_council": "National Medical Commission",
            "specialization": "Internal Medicine",
        },
    )
    assert d_reg.status_code == 201

    d_log = d_client.post("/api/auth/login", json={"email": d_email, "password": "DoctorPassword123!", "role": "doctor"})
    assert d_log.status_code == 200
    d_client.headers["X-CSRF-Token"] = d_log.json()["csrf_token"]

    # 5. Doctor searches Patient ID & Requests Consent
    search_res = d_client.get(f"/api/patients/search/{pat_str}")
    assert search_res.status_code == 200
    assert search_res.json()["patient_id"] == pat_str

    req_res = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": "Comprehensive E2E consultation"},
    )
    assert req_res.status_code == 201
    request_id = req_res.json()["id"]

    # Doctor cannot access workspace yet (pending grant)
    unauth_ws = d_client.get(f"/api/doctors/patients/{pat_id}/workspace")
    assert unauth_ws.status_code == 403

    # 6. Patient reviews and approves consent request
    approve_res = p_client.patch(
        f"/api/consent/requests/{request_id}",
        json={"action": "approve", "duration_hours": 48},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"

    # 7. Doctor opens 3-panel Clinical Workspace
    ws_res = d_client.get(f"/api/doctors/patients/{pat_id}/workspace")
    assert ws_res.status_code == 200
    ws = ws_res.json()
    assert ws["patient"]["patient_id"] == pat_str
    assert len(ws["documents"]) == 2
    assert ws["analysis"]["version_number"] == 1

    # 8. Doctor reviews finding
    rev_res = d_client.post(
        f"/api/reviews/findings/{target_finding_id}",
        json={
            "action": "resolve",
            "explanation": "Reviewed laboratory abnormality. Pharmacotherapy adjusted appropriately.",
        },
    )
    assert rev_res.status_code == 201
    assert rev_res.json()["action"] == "resolve"

    # 9. Patient revokes access grant
    grants = p_client.get("/api/consent/grants").json()
    assert len(grants) >= 1
    grant_id = grants[0]["id"]

    revoke_res = p_client.delete(f"/api/consent/grants/{grant_id}")
    assert revoke_res.status_code == 200

    # 10. Doctor is immediately blocked from workspace
    blocked_ws = d_client.get(f"/api/doctors/patients/{pat_id}/workspace")
    assert blocked_ws.status_code == 403
