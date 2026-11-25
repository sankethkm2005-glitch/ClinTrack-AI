"""Patient router for patient-specific endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, PatientProfile
from app.schemas.auth import PatientProfileOut
from app.utils.dependencies import require_patient, require_doctor

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("/me", response_model=PatientProfileOut)
def get_my_patient_profile(user: User = Depends(require_patient)):
    """Returns the authenticated patient's profile."""
    if not user.patient_profile:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    return user.patient_profile


@router.get("/search/{patient_id}")
def search_patient_by_id(patient_id: str, db: Session = Depends(get_db), doctor: User = Depends(require_doctor)):
    """Allows an authorized doctor to look up a patient by unique ID without disclosing clinical records."""
    profile = db.query(PatientProfile).filter(PatientProfile.patient_id == patient_id.strip()).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID '{patient_id}' not found.",
        )
    return {
        "patient_id": profile.patient_id,
        "full_name": profile.full_name,
        "notice": "Patient identity confirmed. Access to medical records requires an active consent grant.",
    }
