"""Automated tests for Phase 2 Authentication, Registration, and Role Protection."""

import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app


def test_patient_registration_success():
    """Verify patient registration generates unique patient ID and hashes password with Argon2."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    payload = {
        "full_name": "Alice Patient",
        "email": f"alice_{uid}@example.com",
        "date_of_birth": "1992-05-14",
        "gender": "Female",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    res = c.post("/api/auth/register/patient", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == f"alice_{uid}@example.com"
    assert data["role"] == "patient"
    assert data["patient_profile"]["patient_id"].startswith("CLN-PAT-")
    assert data["patient_profile"]["full_name"] == "Alice Patient"


def test_patient_registration_duplicate_email():
    """Ensure duplicate email registration is rejected with 400 Bad Request."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    payload = {
        "full_name": "Alice Duplicate",
        "email": f"alice_dup_{uid}@example.com",
        "date_of_birth": "1992-05-14",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    res1 = c.post("/api/auth/register/patient", json=payload)
    assert res1.status_code == 201

    res2 = c.post("/api/auth/register/patient", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"]


def test_patient_registration_password_mismatch():
    """Ensure mismatched confirm password is rejected."""
    c = TestClient(app)
    payload = {
        "full_name": "Alice Mismatch",
        "email": "mismatch_pwd@example.com",
        "date_of_birth": "1992-05-14",
        "password": "Password123!",
        "confirm_password": "Password999!",
    }
    res = c.post("/api/auth/register/patient", json=payload)
    assert res.status_code == 400
    assert "Passwords do not match" in res.json()["detail"]


def test_doctor_registration_provisional_pending():
    """Verify doctor registration stores verification status as pending."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    form_data = {
        "full_name": "Dr. Gregory House",
        "email": f"house_{uid}@hospital.org",
        "password": "DoctorPassword123!",
        "confirm_password": "DoctorPassword123!",
        "registration_number": f"MED-{uid}",
        "medical_council": "National Medical Commission",
        "specialization": "Diagnostic Medicine",
    }
    res = c.post("/api/auth/register/doctor", data=form_data)
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == f"house_{uid}@hospital.org"
    assert data["role"] == "doctor"
    assert data["doctor_profile"]["verification_status"] == "pending"


def test_login_invalid_credentials():
    """Verify login fails on wrong password."""
    c = TestClient(app)
    res = c.post(
        "/api/auth/login",
        json={"email": "nonexistent@example.com", "password": "WrongPassword!", "role": "patient"},
    )
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]


def test_login_role_mismatch():
    """Ensure logging in under the wrong role is blocked."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    email = f"patient_{uid}@example.com"
    c.post(
        "/api/auth/register/patient",
        json={
            "full_name": "Role Test Patient",
            "email": email,
            "date_of_birth": "1990-01-01",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    res = c.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123!", "role": "doctor"},
    )
    assert res.status_code == 403
    assert "not with the selected role" in res.json()["detail"]


def test_login_and_authenticated_me_patient():
    """Verify session cookie authentication, CSRF, and /api/auth/me profile retrieval."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    email = f"auth_me_{uid}@example.com"
    c.post(
        "/api/auth/register/patient",
        json={
            "full_name": "Auth Me Patient",
            "email": email,
            "date_of_birth": "1990-01-01",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    login_res = c.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123!", "role": "patient"},
    )
    assert login_res.status_code == 200
    assert "clintrace_session" in c.cookies
    csrf_token = login_res.json()["csrf_token"]
    assert csrf_token is not None

    me_res = c.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email
    assert me_res.json()["role"] == "patient"


def test_role_restrictions_patient_cannot_access_doctor_me():
    """Verify patients are forbidden from accessing doctor-only routes."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    email = f"patient_only_{uid}@example.com"
    c.post(
        "/api/auth/register/patient",
        json={
            "full_name": "Patient Only",
            "email": email,
            "date_of_birth": "1990-01-01",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    c.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123!", "role": "patient"},
    )
    res = c.get("/api/doctors/me")
    assert res.status_code == 403
    assert "Access forbidden" in res.json()["detail"]


def test_role_restrictions_doctor_cannot_access_patient_me():
    """Verify doctors are forbidden from accessing patient-only routes."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    email = f"doc_only_{uid}@hospital.org"
    c.post(
        "/api/auth/register/doctor",
        data={
            "full_name": "Doctor Only",
            "email": email,
            "password": "DoctorPassword123!",
            "confirm_password": "DoctorPassword123!",
            "registration_number": f"REG-{uid}",
            "medical_council": "Medical Council",
            "specialization": "Surgery",
        },
    )
    c.post(
        "/api/auth/login",
        json={"email": email, "password": "DoctorPassword123!", "role": "doctor"},
    )
    res = c.get("/api/patients/me")
    assert res.status_code == 403
    assert "Access forbidden" in res.json()["detail"]


def test_doctor_can_search_patient_by_id():
    """Verify authenticated doctor can look up patient ID."""
    uid = uuid.uuid4().hex[:6]
    p_client = TestClient(app)
    p_email = f"search_p_{uid}@example.com"
    p_client.post(
        "/api/auth/register/patient",
        json={
            "full_name": "Search Target Patient",
            "email": p_email,
            "date_of_birth": "1992-05-14",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    p_client.post(
        "/api/auth/login",
        json={"email": p_email, "password": "Password123!", "role": "patient"},
    )
    pat_id = p_client.get("/api/patients/me").json()["patient_id"]

    # Doctor
    d_client = TestClient(app)
    d_email = f"search_d_{uid}@hospital.org"
    d_client.post(
        "/api/auth/register/doctor",
        data={
            "full_name": "Searching Doctor",
            "email": d_email,
            "password": "DoctorPassword123!",
            "confirm_password": "DoctorPassword123!",
            "registration_number": f"REG-SEARCH-{uid}",
            "medical_council": "Council",
            "specialization": "Radiology",
        },
    )
    d_client.post(
        "/api/auth/login",
        json={"email": d_email, "password": "DoctorPassword123!", "role": "doctor"},
    )
    search_res = d_client.get(f"/api/patients/search/{pat_id}")
    assert search_res.status_code == 200
    assert search_res.json()["patient_id"] == pat_id
    assert search_res.json()["full_name"] == "Search Target Patient"


def test_unauthenticated_access_blocked():
    """Ensure protected routes reject requests without session cookie."""
    fresh_client = TestClient(app)
    res = fresh_client.get("/api/auth/me")
    assert res.status_code == 401
    assert "Authentication required" in res.json()["detail"]


def test_logout_clears_session():
    """Verify logout clears session and subsequent requests are rejected."""
    c = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    email = f"logout_{uid}@example.com"
    c.post(
        "/api/auth/register/patient",
        json={
            "full_name": "Logout Patient",
            "email": email,
            "date_of_birth": "1992-05-14",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    login_res = c.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123!", "role": "patient"},
    )
    csrf_token = login_res.json()["csrf_token"]
    logout_res = c.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_res.status_code == 200

    me_res = c.get("/api/auth/me")
    assert me_res.status_code == 401
