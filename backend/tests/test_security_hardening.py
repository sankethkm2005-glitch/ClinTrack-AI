"""Automated regression tests for Security Hardening findings.

Covers:
1. Doctor verification enforcement: pending and rejected doctors get 403 on search, consent requests, and emergency access.
2. Verified doctors are authorized to search and request access.
3. Magic byte signature validation rejects spoofed files for both document uploads and doctor certificates.
4. Oversized certificate uploads are rejected with 400 Bad Request.
5. Invalid doctor and patient registration passwords (<8 chars) and malformed emails are rejected with 400.
6. Duplicate pending consent requests for the same doctor and patient are rejected with 400.
7. Patient ID generation is collision-safe and monotonic even after patient records are deleted.
8. Frontend API header merging behavior and escapeHtml XSS sanitization.
"""

import io
import uuid
from pathlib import Path
import pytest
import fitz
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models.user import User, PatientProfile, DoctorProfile
from app.models.consent import AccessRequest
from app.utils.security import validate_file_magic_bytes


def create_patient_and_doctor(doctor_verification: str = "pending"):
    """Helper to create and login a patient and a doctor with configurable verification status."""
    p_client = TestClient(app)
    d_client = TestClient(app)
    uid = uuid.uuid4().hex[:6]

    # Register & Login Patient
    p_email = f"sec_pat_{uid}@example.com"
    p_reg = p_client.post(
        "/api/auth/register/patient",
        json={
            "full_name": f"Security Patient {uid}",
            "email": p_email,
            "date_of_birth": "1990-01-01",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert p_reg.status_code == 201
    pat_str = p_reg.json()["patient_profile"]["patient_id"]
    pat_id = p_reg.json()["patient_profile"]["id"]

    p_log = p_client.post(
        "/api/auth/login",
        json={"email": p_email, "password": "Password123!", "role": "patient"},
    )
    assert p_log.status_code == 200
    p_client.headers["X-CSRF-Token"] = p_log.json()["csrf_token"]

    # Register & Login Doctor
    d_email = f"sec_doc_{uid}@example.com"
    d_reg = d_client.post(
        "/api/auth/register/doctor",
        data={
            "full_name": f"Dr. Security {uid}",
            "email": d_email,
            "password": "DoctorPassword123!",
            "confirm_password": "DoctorPassword123!",
            "registration_number": f"REG-SEC-{uid}",
            "medical_council": "Medical Council",
            "specialization": "Internal Medicine",
        },
    )
    assert d_reg.status_code == 201
    doc_id = d_reg.json()["id"]

    # Update verification status
    if doctor_verification != "pending":
        db = SessionLocal()
        doc_prof = db.query(DoctorProfile).filter(DoctorProfile.user_id == doc_id).first()
        doc_prof.verification_status = doctor_verification
        db.commit()
        db.close()

    d_log = d_client.post(
        "/api/auth/login",
        json={"email": d_email, "password": "DoctorPassword123!", "role": "doctor"},
    )
    assert d_log.status_code == 200
    d_client.headers["X-CSRF-Token"] = d_log.json()["csrf_token"]

    return p_client, d_client, pat_str, pat_id, doc_id


def test_pending_doctor_blocked_from_patient_search_and_consent_and_emergency():
    """Verify pending doctors receive HTTP 403 on search, access requests, and emergency access."""
    p_client, d_client, pat_str, pat_id, _ = create_patient_and_doctor(doctor_verification="pending")

    # Patient search blocked
    res_search = d_client.get(f"/api/patients/search/{pat_str}")
    assert res_search.status_code == 403
    assert "verification required" in res_search.json()["detail"].lower()

    # Consent request blocked
    res_req = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": "Attempting unauthorized consultation"},
    )
    assert res_req.status_code == 403
    assert "verification required" in res_req.json()["detail"].lower()

    # Emergency access blocked
    res_emerg = d_client.post(
        "/api/consent/emergency-access",
        json={"patient_id_str": pat_str, "reason": "Attempting emergency override without verification"},
    )
    assert res_emerg.status_code == 403
    assert "verification required" in res_emerg.json()["detail"].lower()


def test_rejected_doctor_blocked_from_patient_search_and_consent_and_emergency():
    """Verify rejected doctors receive HTTP 403 on search, access requests, and emergency access."""
    p_client, d_client, pat_str, pat_id, _ = create_patient_and_doctor(doctor_verification="rejected")

    res_search = d_client.get(f"/api/patients/search/{pat_str}")
    assert res_search.status_code == 403
    assert "verification required" in res_search.json()["detail"].lower()

    res_req = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": "Attempting consultation while rejected"},
    )
    assert res_req.status_code == 403

    res_emerg = d_client.post(
        "/api/consent/emergency-access",
        json={"patient_id_str": pat_str, "reason": "Emergency override attempt while rejected"},
    )
    assert res_emerg.status_code == 403


def test_verified_doctor_allowed_patient_search_and_consent():
    """Verify verified doctors are allowed to search patients and submit consent requests."""
    p_client, d_client, pat_str, pat_id, _ = create_patient_and_doctor(doctor_verification="verified")

    res_search = d_client.get(f"/api/patients/search/{pat_str}")
    assert res_search.status_code == 200
    assert res_search.json()["patient_id"] == pat_str

    res_req = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": "Valid clinical examination consultation"},
    )
    assert res_req.status_code == 201
    assert res_req.json()["status"] == "pending"


def test_duplicate_pending_consent_request_rejected():
    """Verify submitting a second pending consent request for the same patient returns HTTP 400."""
    p_client, d_client, pat_str, pat_id, _ = create_patient_and_doctor(doctor_verification="verified")

    # First request succeeds
    res1 = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": "First clinical consultation request"},
    )
    assert res1.status_code == 201

    # Second request while first is pending must fail with 400
    res2 = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": "Duplicate consultation request"},
    )
    assert res2.status_code == 400
    assert "pending access request already exists" in res2.json()["detail"].lower()


def test_spoofed_file_magic_bytes_rejected_on_document_upload():
    """Verify files with mismatched magic bytes (e.g. plain text or executable renamed to .pdf) are rejected."""
    p_client, _, _, _, _ = create_patient_and_doctor(doctor_verification="verified")

    fake_pdf = b"NOT_A_REAL_PDF_JUST_PLAIN_TEXT_PAYLOAD"
    res = p_client.post(
        "/api/documents/upload",
        files=[("files", ("malicious.pdf", io.BytesIO(fake_pdf), "application/pdf"))],
        data={"document_type": "prescription"},
    )
    assert res.status_code == 400
    assert "signature does not match" in res.json()["detail"].lower()


def test_spoofed_certificate_magic_bytes_rejected_on_doctor_registration():
    """Verify doctor registration rejects certificates with mismatched magic bytes."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    fake_cert = b"THIS_IS_NOT_A_VALID_IMAGE_OR_PDF_CERTIFICATE"

    res = c.post(
        "/api/auth/register/doctor",
        data={
            "full_name": f"Dr. Spoof {uid}",
            "email": f"spoof_{uid}@hospital.org",
            "password": "DoctorPassword123!",
            "confirm_password": "DoctorPassword123!",
            "registration_number": f"REG-SPOOF-{uid}",
            "medical_council": "Medical Council",
            "specialization": "General Medicine",
        },
        files={"certificate": ("certificate.pdf", io.BytesIO(fake_cert), "application/pdf")},
    )
    assert res.status_code == 400
    assert "signature does not match" in res.json()["detail"].lower()


def test_oversized_doctor_certificate_rejected():
    """Verify certificate exceeding MAX_UPLOAD_SIZE_MB is rejected with 400."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    # Create valid PDF header but oversized
    oversized_bytes = b"%PDF-" + b"0" * (settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1024)

    res = c.post(
        "/api/auth/register/doctor",
        data={
            "full_name": f"Dr. BigCert {uid}",
            "email": f"bigcert_{uid}@hospital.org",
            "password": "DoctorPassword123!",
            "confirm_password": "DoctorPassword123!",
            "registration_number": f"REG-BIG-{uid}",
            "medical_council": "Medical Council",
            "specialization": "Radiology",
        },
        files={"certificate": ("oversized.pdf", io.BytesIO(oversized_bytes), "application/pdf")},
    )
    assert res.status_code == 400
    assert "limit" in res.json()["detail"].lower()


def test_invalid_doctor_and_patient_registration_validations():
    """Verify password length >= 8 and email format validation for both patient and doctor registration."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]

    # Short password for patient (rejected by pydantic or route with 422/400)
    res_pat_pwd = c.post(
        "/api/auth/register/patient",
        json={
            "full_name": "Short Pwd Patient",
            "email": f"short_{uid}@example.com",
            "date_of_birth": "1990-01-01",
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert res_pat_pwd.status_code in (400, 422)

    # Invalid email for patient
    res_pat_email = c.post(
        "/api/auth/register/patient",
        json={
            "full_name": "Bad Email Patient",
            "email": "not-an-email",
            "date_of_birth": "1990-01-01",
            "password": "ValidPassword123!",
            "confirm_password": "ValidPassword123!",
        },
    )
    assert res_pat_email.status_code in (400, 422)

    # Short password for doctor
    res_doc_pwd = c.post(
        "/api/auth/register/doctor",
        data={
            "full_name": "Dr. Short",
            "email": f"doc_short_{uid}@hospital.org",
            "password": "pass",
            "confirm_password": "pass",
            "registration_number": f"REG-{uid}",
            "medical_council": "Council",
            "specialization": "Surgery",
        },
    )
    assert res_doc_pwd.status_code == 400
    assert "at least 8 characters" in res_doc_pwd.json()["detail"]

    # Invalid email for doctor
    res_doc_email = c.post(
        "/api/auth/register/doctor",
        data={
            "full_name": "Dr. BadEmail",
            "email": "bad_doctor_email",
            "password": "ValidPassword123!",
            "confirm_password": "ValidPassword123!",
            "registration_number": f"REG-{uid}",
            "medical_council": "Council",
            "specialization": "Surgery",
        },
    )
    assert res_doc_email.status_code == 400
    assert "invalid email" in res_doc_email.json()["detail"].lower()


def test_patient_id_generation_collision_safe_after_deletion():
    """Verify that deleting an intermediate patient record does not cause duplicate ID generation."""
    c = TestClient(app)
    uid1 = uuid.uuid4().hex[:6]
    uid2 = uuid.uuid4().hex[:6]

    res1 = c.post(
        "/api/auth/register/patient",
        json={
            "full_name": f"Pat 1 {uid1}",
            "email": f"pat1_{uid1}@example.com",
            "date_of_birth": "1990-01-01",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert res1.status_code == 201
    pid1 = res1.json()["patient_profile"]["patient_id"]
    pat1_user_id = res1.json()["id"]

    res2 = c.post(
        "/api/auth/register/patient",
        json={
            "full_name": f"Pat 2 {uid2}",
            "email": f"pat2_{uid2}@example.com",
            "date_of_birth": "1990-01-01",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert res2.status_code == 201
    pid2 = res2.json()["patient_profile"]["patient_id"]

    # Simulate record deletion of patient 2
    db = SessionLocal()
    p2_prof = db.query(PatientProfile).filter(PatientProfile.patient_id == pid2).first()
    if p2_prof:
        u2 = db.query(User).filter(User.id == p2_prof.user_id).first()
        db.delete(p2_prof)
        if u2:
            db.delete(u2)
        db.commit()
    db.close()

    # Register a new patient 3
    uid3 = uuid.uuid4().hex[:6]
    res3 = c.post(
        "/api/auth/register/patient",
        json={
            "full_name": f"Pat 3 {uid3}",
            "email": f"pat3_{uid3}@example.com",
            "date_of_birth": "1990-01-01",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert res3.status_code == 201
    pid3 = res3.json()["patient_profile"]["patient_id"]

    # Assert new patient ID does not collide with pid1 and is strictly valid
    assert pid3 != pid1
    assert pid3.startswith("CLN-PAT-")
    # Verify unique in DB
    db = SessionLocal()
    count = db.query(PatientProfile).filter(PatientProfile.patient_id == pid3).count()
    db.close()
    assert count == 1


def test_validate_file_magic_bytes_utility():
    """Verify validate_file_magic_bytes function directly for various valid and invalid formats."""
    # Valid PDF
    validate_file_magic_bytes(b"%PDF-1.4\n...", "document.pdf")
    # Valid PNG
    validate_file_magic_bytes(b"\x89PNG\r\n\x1a\n\x00\x00", "image.png")
    # Valid JPEG
    validate_file_magic_bytes(b"\xff\xd8\xff\xe0\x00", "photo.jpg")
    validate_file_magic_bytes(b"\xff\xd8\xff\xe1\x00", "photo.jpeg")

    # Mismatched extensions
    with pytest.raises(Exception) as exc1:
        validate_file_magic_bytes(b"\x89PNG\r\n\x1a\n", "document.pdf")
    assert "signature does not match" in str(exc1.value).lower()

    with pytest.raises(Exception) as exc2:
        validate_file_magic_bytes(b"%PDF-1.4", "image.png")
    assert "signature does not match" in str(exc2.value).lower()

    with pytest.raises(Exception) as exc3:
        validate_file_magic_bytes(b"MZ\x90\x00", "executable.exe")
    assert "unsupported file format" in str(exc3.value).lower()


def test_xss_payload_in_fields_and_frontend_escape_html_present():
    """Verify that potentially malicious HTML input strings are safely preserved in API responses and frontend api.js provides escapeHtml."""
    p_client, d_client, pat_str, pat_id, doc_id = create_patient_and_doctor(doctor_verification="verified")

    # Submit access request with script tag in reason
    xss_reason = "<script>alert('xss')</script> & <b>urgent</b> review"
    res_req = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": xss_reason},
    )
    assert res_req.status_code == 201
    assert res_req.json()["reason"] == xss_reason

    # Verify patient retrieving the request receives the exact string without server crash
    p_reqs = p_client.get("/api/consent/requests")
    assert p_reqs.status_code == 200
    matched = [r for r in p_reqs.json() if r["reason"] == xss_reason]
    assert len(matched) == 1

    # Verify frontend js/api.js contains escapeHtml definition and header fix
    api_js_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "js" / "api.js"
    assert api_js_path.exists(), f"api.js not found at {api_js_path}"
    content = api_js_path.read_text(encoding="utf-8")
    assert "function escapeHtml" in content
    assert "window.escapeHtml = escapeHtml" in content
    assert "X-CSRF-Token" in content


def test_audit_history_access_and_isolation():
    """Verify GET /api/audit/history returns only events authorized for the authenticated patient or doctor."""
    p1_client, d1_client, pat1_str, pat1_id, doc1_id = create_patient_and_doctor(doctor_verification="verified")
    p2_client, _, _, pat2_id, _ = create_patient_and_doctor(doctor_verification="verified")

    # Doctor 1 requests access to Patient 1 and Patient 1 approves
    req_res = d1_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat1_str, "reason": "Audit trail verification test"},
    )
    assert req_res.status_code == 201
    req_id = req_res.json()["id"]

    app_res = p1_client.patch(
        f"/api/consent/requests/{req_id}",
        json={"action": "approve", "duration_hours": 24},
    )
    assert app_res.status_code == 200

    # Patient 1 should see access_requested and access_granted for their own record
    p1_audit = p1_client.get("/api/audit/history")
    assert p1_audit.status_code == 200
    p1_actions = [ev["action"] for ev in p1_audit.json()]
    assert "access_requested" in p1_actions
    assert "access_granted" in p1_actions
    for ev in p1_audit.json():
        assert ev["resource_id"] == str(pat1_id)

    # Patient 2 must NOT see Patient 1's audit events
    p2_audit = p2_client.get("/api/audit/history")
    assert p2_audit.status_code == 200
    for ev in p2_audit.json():
        assert ev["resource_id"] != str(pat1_id)

    # Doctor 1 sees events they initiated
    d1_audit = d1_client.get("/api/audit/history")
    assert d1_audit.status_code == 200
    assert any(ev["action"] == "access_requested" for ev in d1_audit.json())


def test_expired_consent_grant_blocks_doctor_workspace():
    """Verify expired consent grants are marked inactive and block doctor workspace access with HTTP 403."""
    from datetime import datetime, timedelta, timezone
    from app.models.consent import AccessGrant

    p_client, d_client, pat_str, pat_id, doc_id = create_patient_and_doctor(doctor_verification="verified")

    # Insert an already-expired grant directly in DB
    db = SessionLocal()
    expired_grant = AccessGrant(
        doctor_id=doc_id,
        patient_id=pat_id,
        scope="full_records",
        is_emergency=False,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db.add(expired_grant)
    db.commit()
    db.close()

    # Doctor workspace access must be forbidden (403)
    ws_res = d_client.get(f"/api/doctors/patients/{pat_id}/workspace")
    assert ws_res.status_code == 403

    # Active patients list for doctor must exclude expired grant
    doc_patients = d_client.get("/api/doctors/patients")
    assert doc_patients.status_code == 200
    assert all(g["patient_id"] != pat_id for g in doc_patients.json())

    # Patient's grants list must report is_active == False
    pat_grants = p_client.get("/api/consent/grants")
    assert pat_grants.status_code == 200
    assert len(pat_grants.json()) >= 1
    assert pat_grants.json()[0]["is_active"] is False


def test_notifications_mark_read_flow():
    """Verify patient and doctor notifications can be retrieved and marked as read."""
    p_client, d_client, pat_str, pat_id, _ = create_patient_and_doctor(doctor_verification="verified")

    # Doctor submits consent request -> triggers notification for Patient
    req_res = d_client.post(
        "/api/consent/requests",
        json={"patient_id_str": pat_str, "reason": "Notification mark-read test"},
    )
    assert req_res.status_code == 201
    req_id = req_res.json()["id"]

    # Patient retrieves unread notification and marks it as read
    p_notifs = p_client.get("/api/notifications")
    assert p_notifs.status_code == 200
    assert len(p_notifs.json()) >= 1
    unread_notif = p_notifs.json()[0]
    assert unread_notif["is_read"] is False

    mark_res = p_client.patch(f"/api/notifications/{unread_notif['id']}/read")
    assert mark_res.status_code == 200

    p_notifs_after = p_client.get("/api/notifications")
    assert any(n["id"] == unread_notif["id"] and n["is_read"] is True for n in p_notifs_after.json())

    # Patient approves request -> triggers notification for Doctor
    app_res = p_client.patch(
        f"/api/consent/requests/{req_id}",
        json={"action": "approve", "duration_hours": 24},
    )
    assert app_res.status_code == 200

    d_notifs = d_client.get("/api/notifications")
    assert d_notifs.status_code == 200
    assert len(d_notifs.json()) >= 1
    d_notif = d_notifs.json()[0]
    assert d_notif["is_read"] is False

    d_mark = d_client.patch(f"/api/notifications/{d_notif['id']}/read")
    assert d_mark.status_code == 200

    d_notifs_after = d_client.get("/api/notifications")
    assert any(n["id"] == d_notif["id"] and n["is_read"] is True for n in d_notifs_after.json())


def test_frontend_responsive_css_and_landing_cleanup():
    """Verify responsive breakpoints, audit history integration, and landing page branding cleanup."""
    root_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

    styles_css = (root_dir / "css" / "styles.css").read_text(encoding="utf-8")
    assert "@media (max-width: 960px)" in styles_css
    assert "@media (max-width: 640px)" in styles_css

    index_html = (root_dir / "index.html").read_text(encoding="utf-8")
    assert "Phase 1: Foundation" not in index_html

    consent_html = (root_dir / "patient" / "consent.html").read_text(encoding="utf-8")
    assert "/audit/history" in consent_html

    doc_dash_html = (root_dir / "doctor" / "dashboard.html").read_text(encoding="utf-8")
    assert "/notifications" in doc_dash_html


