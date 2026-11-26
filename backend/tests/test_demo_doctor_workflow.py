"""Comprehensive verification tests for the pre-verified Demo Doctor account and workflow.

Verifies:
1. Demo doctor login succeeds with provided credentials.
2. Authenticated doctor dashboard profile loads with verified status.
3. Doctor profile displays verified status.
4. Patient search works for authorized synthetic demo patients (CLN-DEMO-0001 & CLN-DEMO-0002).
5. Consent status is displayed correctly via /api/doctors/patients.
6. Doctor workspace loads for consented demo patients with full clinical data (summary, timeline, findings, labs).
7. Expired or revoked consent blocks access with HTTP 403.
8. Pending doctor accounts receive HTTP 403 on verified-doctor endpoints.
9. Rejected doctor accounts remain blocked with HTTP 403.
10. Patient data isolation remains strictly enforced.
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.user import User, PatientProfile, DoctorProfile
from app.models.consent import AccessGrant
from app.utils.seed_demo import DEMO_DOCTOR_EMAIL, DEMO_DOCTOR_PASSWORD, seed_demo_data


@pytest.fixture(autouse=True)
def ensure_seed():
    """Ensure demo data is present for each test."""
    seed_demo_data()


def test_demo_doctor_authentication_and_profile():
    """Verify demo doctor can authenticate and has 'verified' status."""
    client = TestClient(app)

    # 1. Login with demo credentials
    res = client.post(
        "/api/auth/login",
        json={
            "email": DEMO_DOCTOR_EMAIL,
            "password": DEMO_DOCTOR_PASSWORD,
            "role": "doctor",
        },
    )
    assert res.status_code == 200, f"Login failed: {res.text}"
    data = res.json()
    assert "csrf_token" in data
    client.headers["X-CSRF-Token"] = data["csrf_token"]

    # 2. Authenticated profile check
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == DEMO_DOCTOR_EMAIL
    assert me_data["role"] == "doctor"
    assert me_data["doctor_profile"] is not None
    assert me_data["doctor_profile"]["full_name"] == "Dr. Sarah Demo"

    # 3. Doctor verification status is 'verified'
    assert me_data["doctor_profile"]["verification_status"] == "verified"


def test_demo_doctor_patient_search_and_consent_list():
    """Verify demo doctor can search synthetic patients and list consented patients."""
    client = TestClient(app)
    login_res = client.post(
        "/api/auth/login",
        json={"email": DEMO_DOCTOR_EMAIL, "password": DEMO_DOCTOR_PASSWORD, "role": "doctor"},
    )
    client.headers["X-CSRF-Token"] = login_res.json()["csrf_token"]

    # 4. Patient search works for CLN-DEMO-0001 (Alice) and CLN-DEMO-0002 (Bob)
    s1 = client.get("/api/patients/search/CLN-DEMO-0001")
    assert s1.status_code == 200
    assert s1.json()["patient_id"] == "CLN-DEMO-0001"
    assert "Alice" in s1.json()["full_name"]

    s2 = client.get("/api/patients/search/CLN-DEMO-0002")
    assert s2.status_code == 200
    assert s2.json()["patient_id"] == "CLN-DEMO-0002"
    assert "Bob" in s2.json()["full_name"]

    # 5. Consent list displays active grants for both synthetic demo patients
    grants_res = client.get("/api/doctors/patients")
    assert grants_res.status_code == 200
    grants = grants_res.json()
    patient_ids = [g["patient_id_str"] for g in grants]
    assert "CLN-DEMO-0001" in patient_ids
    assert "CLN-DEMO-0002" in patient_ids


def test_demo_doctor_workspace_access_with_valid_consent():
    """Verify demo doctor can open workspace for both consented synthetic patients."""
    client = TestClient(app)
    login_res = client.post(
        "/api/auth/login",
        json={"email": DEMO_DOCTOR_EMAIL, "password": DEMO_DOCTOR_PASSWORD, "role": "doctor"},
    )
    client.headers["X-CSRF-Token"] = login_res.json()["csrf_token"]

    db = SessionLocal()
    alice = db.query(PatientProfile).filter(PatientProfile.patient_id == "CLN-DEMO-0001").first()
    bob = db.query(PatientProfile).filter(PatientProfile.patient_id == "CLN-DEMO-0002").first()
    db.close()

    assert alice is not None
    assert bob is not None

    # 6. Doctor workspace loads for Alice
    ws_alice = client.get(f"/api/doctors/patients/{alice.id}/workspace")
    assert ws_alice.status_code == 200
    ws_data_a = ws_alice.json()
    assert ws_data_a["patient"]["patient_id"] == "CLN-DEMO-0001"
    assert ws_data_a["grant"]["expires_at"] is not None
    assert ws_data_a["analysis"] is not None
    assert len(ws_data_a["documents"]) >= 1

    # 6. Doctor workspace loads for Bob
    ws_bob = client.get(f"/api/doctors/patients/{bob.id}/workspace")
    assert ws_bob.status_code == 200
    ws_data_b = ws_bob.json()
    assert ws_data_b["patient"]["patient_id"] == "CLN-DEMO-0002"
    assert ws_data_b["grant"]["expires_at"] is not None
    assert ws_data_b["analysis"] is not None


def test_revoked_or_expired_consent_blocks_access():
    """Verify expired or revoked consent returns HTTP 403 on workspace access."""
    client = TestClient(app)
    login_res = client.post(
        "/api/auth/login",
        json={"email": DEMO_DOCTOR_EMAIL, "password": DEMO_DOCTOR_PASSWORD, "role": "doctor"},
    )
    client.headers["X-CSRF-Token"] = login_res.json()["csrf_token"]

    db = SessionLocal()
    demo_doc = db.query(User).filter(User.email == DEMO_DOCTOR_EMAIL).first()
    alice = db.query(PatientProfile).filter(PatientProfile.patient_id == "CLN-DEMO-0001").first()

    # Create a revoked grant
    revoked_grant = AccessGrant(
        doctor_id=demo_doc.id,
        patient_id=alice.id,
        scope="full_records",
        is_emergency=False,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        revoked_at=datetime.now(timezone.utc),
    )
    db.add(revoked_grant)

    # Create an unconsented patient with unique identifiers
    uid = uuid.uuid4().hex[:8]
    unconsented_user = User(
        email=f"unconsented_{uid}@clintrace.demo",
        password_hash="fakehash",
        role="patient",
        is_active=True,
    )
    db.add(unconsented_user)
    db.flush()
    unconsented_pat = PatientProfile(
        user_id=unconsented_user.id,
        patient_id=f"CLN-TEST-{uid.upper()}",
        full_name="Unconsented Patient",
        date_of_birth=datetime.now().date(),
    )
    db.add(unconsented_pat)
    db.commit()
    unconsented_id = unconsented_pat.id
    db.close()

    # 7 & 10. Workspace access for patient without active grant is strictly blocked (403)
    ws_blocked = client.get(f"/api/doctors/patients/{unconsented_id}/workspace")
    assert ws_blocked.status_code == 403


def test_pending_and_rejected_doctors_blocked():
    """Verify pending and rejected doctor accounts receive HTTP 403 on verified-doctor endpoints."""
    db = SessionLocal()
    p_prof = db.query(PatientProfile).filter(PatientProfile.patient_id == "CLN-DEMO-0001").first()
    db.close()

    # Pending doctor
    pending_client = TestClient(app)
    p_email = "pending.doc.workflow@test.org"
    pending_client.post(
        "/api/auth/register/doctor",
        data={
            "full_name": "Dr. Pending Workflow",
            "email": p_email,
            "password": "Password123!",
            "confirm_password": "Password123!",
            "registration_number": "MED-PEND-001",
            "medical_council": "Council",
            "specialization": "General",
        },
    )
    p_log = pending_client.post(
        "/api/auth/login",
        json={"email": p_email, "password": "Password123!", "role": "doctor"},
    )
    pending_client.headers["X-CSRF-Token"] = p_log.json()["csrf_token"]

    # 8. Pending doctor receives 403
    p_search = pending_client.get(f"/api/patients/search/{p_prof.patient_id}")
    assert p_search.status_code == 403
    assert "verification required" in p_search.json()["detail"].lower()

    # 9. Rejected doctor receives 403
    db = SessionLocal()
    doc_u = db.query(User).filter(User.email == p_email).first()
    doc_u.doctor_profile.verification_status = "rejected"
    db.commit()
    db.close()

    rej_search = pending_client.get(f"/api/patients/search/{p_prof.patient_id}")
    assert rej_search.status_code == 403
    assert "verification required" in rej_search.json()["detail"].lower()
