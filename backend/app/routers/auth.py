"""Authentication router for registration, login, logout, and session check."""

import os
import re
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.database import get_db
from app.models.user import User, PatientProfile, DoctorProfile
from app.schemas.auth import (
    PatientRegisterRequest,
    DoctorRegisterRequest,
    LoginRequest,
    UserOut,
)
from app.utils.security import (
    hash_password,
    verify_password,
    generate_patient_id,
    generate_csrf_token,
    create_session_token,
    validate_file_magic_bytes,
)
from app.utils.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z0-9\-\.]+$")


@router.get("/csrf-token")
def get_csrf_token():
    """Provides a fresh CSRF token for forms before authentication or state mutation."""
    return {"csrf_token": generate_csrf_token()}


@router.post("/register/patient", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_patient(payload: PatientRegisterRequest, db: Session = Depends(get_db)):
    """Register a new patient account with a uniquely generated patient ID."""
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    email_clean = payload.email.lower().strip()
    if not EMAIL_REGEX.match(email_clean):
        raise HTTPException(status_code=400, detail="Invalid email address format.")

    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = User(
        email=email_clean,
        password_hash=hash_password(payload.password),
        role="patient",
    )
    db.add(user)
    db.flush()

    # Collision-safe patient ID generation that survives profile deletions
    highest_num = 1000
    all_profiles = db.query(PatientProfile.patient_id).all()
    for (pid,) in all_profiles:
        if pid and pid.startswith("CLN-PAT-"):
            try:
                num = int(pid.split("-")[-1])
                if num > highest_num:
                    highest_num = num
            except ValueError:
                pass

    next_num = highest_num + 1
    generated_id = generate_patient_id(next_num)
    while db.query(PatientProfile).filter(PatientProfile.patient_id == generated_id).first():
        next_num += 1
        generated_id = generate_patient_id(next_num)

    profile = PatientProfile(
        user_id=user.id,
        patient_id=generated_id,
        full_name=payload.full_name.strip(),
        date_of_birth=payload.date_of_birth,
        gender=payload.gender.strip() if payload.gender else None,
    )
    db.add(profile)
    db.commit()
    db.refresh(user)
    return user


@router.post("/register/doctor", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register_doctor(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    registration_number: str = Form(...),
    medical_council: str = Form(...),
    specialization: str = Form(...),
    certificate: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    """Register a doctor account with certificate upload and provisional pending verification."""
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    email_clean = email.lower().strip()
    if not EMAIL_REGEX.match(email_clean):
        raise HTTPException(status_code=400, detail="Invalid email address format.")

    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    certificate_saved_path = None
    if certificate and certificate.filename:
        # Validate extension
        ext = Path(certificate.filename).suffix.lower()
        if ext not in [".pdf", ".png", ".jpg", ".jpeg"]:
            raise HTTPException(
                status_code=400,
                detail="Supported certificate formats are PDF, PNG, JPG, and JPEG only.",
            )

        cert_bytes = await certificate.read()
        max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(cert_bytes) > max_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Certificate file exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit.",
            )

        validate_file_magic_bytes(cert_bytes, certificate.filename)

        # Save to private upload storage
        upload_dir = settings.resolved_upload_dir / "doctor_certificates"
        upload_dir.mkdir(parents=True, exist_ok=True)
        filename = f"cert_{email_clean.replace('@', '_at_')}_{os.urandom(4).hex()}{ext}"
        destination = upload_dir / filename
        destination.write_bytes(cert_bytes)
        certificate_saved_path = str(destination)

    user = User(
        email=email_clean,
        password_hash=hash_password(password),
        role="doctor",
    )
    db.add(user)
    db.flush()

    doctor_prof = DoctorProfile(
        user_id=user.id,
        full_name=full_name.strip(),
        registration_number=registration_number.strip(),
        medical_council=medical_council.strip(),
        specialization=specialization.strip(),
        certificate_path=certificate_saved_path,
        verification_status="pending",
    )
    db.add(doctor_prof)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Authenticate user, verify role, and set secure HTTP-only session cookie."""
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.role != payload.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account exists, but not with the selected role '{payload.role}'.",
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled.")

    csrf_token = generate_csrf_token()
    session_token = create_session_token(user.id, user.role, csrf_token)

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        max_age=settings.SESSION_EXPIRE_MINUTES * 60,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )

    return {
        "status": "success",
        "message": "Logged in successfully",
        "role": user.role,
        "csrf_token": csrf_token,
        "redirect_url": "/patient/dashboard.html" if user.role == "patient" else "/doctor/dashboard.html",
    }


@router.post("/logout")
def logout(response: Response, user: User = Depends(get_current_user)):
    """Clear the session cookie."""
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
    return {"status": "success", "message": "Logged out successfully"}


@router.get("/me", response_model=UserOut)
def get_current_user_profile(user: User = Depends(get_current_user)):
    """Return profile for the currently logged-in user."""
    return user
