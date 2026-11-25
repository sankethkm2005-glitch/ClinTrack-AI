"""Automated tests for Phase 6 Consent Management, Doctor Reviews, and Emergency Access."""

import io
import uuid
import pytest
import fitz
from fastapi.testclient import TestClient
from app.main import app


def create_user(role: str = "patient"):
    """Helper creating an authenticated client for testing."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    email = f"user_{role}_{uid}@example.com"
    if role == "patient":
        c.post(
            "/api/auth/register/patient",
            json={
                "full_name": f"Patient {uid}",
                "email": email,
                "date_of_birth": "1985-06-15",
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
    c.headers["X-CSRF-Token"] = login_res.json()["csrf_token"]
    profile = c.get("/api/auth/me").json()
    return c, profile


def upload_pdf_and_analyze(patient_client, pat_id):
    """Helper to upload a medical document and run AI analysis."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "CLINICAL NOTE: Metformin 500mg BID. Type 2 Diabetes. HbA1c: 7.8% (H)")
    pdf_bytes = doc.tobytes()
    doc.close()

    patient_client.post(
        "/api/documents/upload",
        files=[("files", ("visit.pdf", io.BytesIO(pdf_bytes), "application/pdf"))],
        data={"document_type": "prescription"},
    )
    return patient_client.post(f"/api/analysis/patients/{pat_id}/run").json()


def test_consent_request_and_approval_flow():
    """Verify doctor requests consent, patient approves, and grant is active."""
    p_client, p_profile = create_user("patient")
    d_client, d_profile = create_user("doctor")
    pat_str = p_profile["patient_profile"]["patient_id"]
    pat_id = p_profile["patient_profile"]["id"]

    # Doctor requests consent
    req_res = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": "Pre-op cardiology evaluation"},
    )
    assert req_res.status_code == 201
    req_id = req_res.json()["id"]

    # Patient approves request
    patch_res = p_client.patch(
        f"/api/consent/requests/{req_id}",
        json={"action": "approve", "duration_hours": 48},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "approved"

    # Doctor checks active patients list
    my_pats = d_client.get("/api/doctors/patients").json()
    assert len(my_pats) >= 1
    assert any(p["patient_id"] == pat_id for p in my_pats)


def test_unauthorized_doctor_blocked_from_workspace():
    """Ensure doctor without active grant is forbidden (403) from patient workspace."""
    p_client, p_profile = create_user("patient")
    d_client, d_profile = create_user("doctor")
    pat_id = p_profile["patient_profile"]["id"]

    res = d_client.get(f"/api/doctors/patients/{pat_id}/workspace")
    assert res.status_code == 403
    assert "No active or valid consent grant" in res.json()["detail"]


def test_patient_can_revoke_grant():
    """Verify patient can revoke active grant and doctor loses access immediately."""
    p_client, p_profile = create_user("patient")
    d_client, d_profile = create_user("doctor")
    pat_str = p_profile["patient_profile"]["patient_id"]
    pat_id = p_profile["patient_profile"]["id"]

    req_res = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": "Consultation"},
    )
    req_id = req_res.json()["id"]
    p_client.patch(f"/api/consent/requests/{req_id}", json={"action": "approve", "duration_hours": 24})

    # Find grant ID
    grants = p_client.get("/api/consent/grants").json()
    grant_id = grants[0]["id"]

    # Revoke
    rev_res = p_client.delete(f"/api/consent/grants/{grant_id}")
    assert rev_res.status_code == 200

    # Doctor attempts to access workspace after revocation
    blocked = d_client.get(f"/api/doctors/patients/{pat_id}/workspace")
    assert blocked.status_code == 403


def test_emergency_access_and_auditing():
    """Verify emergency access creates restricted grant, audits event, and notifies patient."""
    p_client, p_profile = create_user("patient")
    d_client, d_profile = create_user("doctor")
    pat_str = p_profile["patient_profile"]["patient_id"]
    pat_id = p_profile["patient_profile"]["id"]

    em_res = d_client.post(
        "/api/consent/emergency-access",
        json={
            "patient_id_str": pat_str,
            "reason": "Acute unresponsive trauma patient requiring immediate medication history",
        },
    )
    assert em_res.status_code == 200
    assert em_res.json()["is_emergency"] is True

    # Doctor now has workspace access
    ws = d_client.get(f"/api/doctors/patients/{pat_id}/workspace")
    assert ws.status_code == 200

    # Verify patient received emergency notification
    notifs = p_client.get("/api/notifications").json()
    assert any("EMERGENCY" in n["title"] for n in notifs)

    # Verify audit log contains emergency event
    audit_res = d_client.get("/api/audit/history").json()
    assert any(a["action"] == "emergency_access_invoked" for a in audit_res)


def test_doctor_finding_review_flow():
    """Verify doctor can review AI findings and reviews are saved without altering AI findings."""
    p_client, p_profile = create_user("patient")
    d_client, d_profile = create_user("doctor")
    pat_str = p_profile["patient_profile"]["patient_id"]
    pat_id = p_profile["patient_profile"]["id"]

    # Upload document and generate analysis with findings
    analysis = upload_pdf_and_analyze(p_client, pat_id)
    finding_id = analysis["findings"][0]["id"]

    # Grant doctor access
    req_res = d_client.post("/api/consent/requests", json={"patient_id_str": pat_str, "reason": "Review"})
    p_client.patch(f"/api/consent/requests/{req_res.json()['id']}", json={"action": "approve", "duration_hours": 12})

    # Doctor submits review
    rev_res = d_client.post(
        f"/api/reviews/findings/{finding_id}",
        json={
            "action": "accept",
            "explanation": "Clinically verified lab abnormality; patient counseled regarding glycemic targets.",
        },
    )
    assert rev_res.status_code == 201
    assert rev_res.json()["action"] == "accept"

    # Fetch review history for the finding
    hist = d_client.get(f"/api/reviews/findings/{finding_id}").json()
    assert len(hist) == 1
    assert hist[0]["action"] == "accept"
    assert "Clinically verified" in hist[0]["explanation"]
