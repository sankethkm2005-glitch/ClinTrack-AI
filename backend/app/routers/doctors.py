"""Doctor router for doctor-specific endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.consent import AccessGrant
from app.models.document import Document
from app.models.analysis import AIAnalysis
from app.schemas.auth import DoctorProfileOut
from app.schemas.consent import AccessGrantOut
from app.schemas.document import DocumentOut
from app.schemas.analysis import AIAnalysisOut
from app.utils.dependencies import require_doctor

router = APIRouter(prefix="/doctors", tags=["Doctors"])


def _is_grant_active(grant: AccessGrant) -> bool:
    """Helper to check if an access grant is currently active regardless of tz offset."""
    if grant.revoked_at is not None:
        return False
    exp = grant.expires_at
    now = datetime.now(timezone.utc)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > now



@router.get("/me", response_model=DoctorProfileOut)

def get_my_doctor_profile(user: User = Depends(require_doctor)):
    """Returns the authenticated doctor's profile."""
    if not user.doctor_profile:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")
    return user.doctor_profile


@router.get("/patients", response_model=list[AccessGrantOut])
def get_my_authorized_patients(
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    """Returns list of patients with active, non-expired access grants for this doctor."""
    all_grants = (
        db.query(AccessGrant)
        .filter(
            AccessGrant.doctor_id == doctor.id,
            AccessGrant.revoked_at == None,
        )
        .order_by(AccessGrant.created_at.desc())
        .all()
    )
    grants = [g for g in all_grants if _is_grant_active(g)]

    results = []
    for g in grants:
        results.append(
            AccessGrantOut(
                id=g.id,
                doctor_id=g.doctor_id,
                doctor_name=doctor.doctor_profile.full_name if doctor.doctor_profile else "Doctor",
                patient_id=g.patient_id,
                patient_id_str=g.patient.patient_id if g.patient else None,
                patient_name=g.patient.full_name if g.patient else None,
                scope=g.scope,
                is_emergency=g.is_emergency,
                is_active=True,
                expires_at=g.expires_at,
                revoked_at=None,
                created_at=g.created_at,
            )
        )
    return results


@router.get("/patients/{patient_id}/workspace")
def get_clinical_workspace(
    patient_id: int,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    """
    Returns full clinical workspace payload for the 3-panel UI:
    LEFT: Timeline + Documents
    CENTRE: Medical summary + Latest Analysis
    RIGHT: AI Findings & Discrepancies
    """
    matching_grants = (
        db.query(AccessGrant)
        .filter(
            AccessGrant.doctor_id == doctor.id,
            AccessGrant.patient_id == patient_id,
            AccessGrant.revoked_at == None,
        )
        .all()
    )
    active_grant = next((g for g in matching_grants if _is_grant_active(g)), None)
    if not active_grant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: No active or valid consent grant for this patient.",
        )

    # Documents
    docs = (
        db.query(Document)
        .filter(Document.patient_id == patient_id, Document.is_deleted == False)
        .order_by(Document.uploaded_at.desc())
        .all()
    )

    # Latest Analysis
    analysis = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.patient_id == patient_id)
        .order_by(AIAnalysis.version_number.desc())
        .first()
    )

    return {
        "grant": {
            "is_emergency": active_grant.is_emergency,
            "expires_at": active_grant.expires_at,
            "scope": active_grant.scope,
        },
        "patient": {
            "id": active_grant.patient.id,
            "patient_id": active_grant.patient.patient_id,
            "full_name": active_grant.patient.full_name,
            "date_of_birth": active_grant.patient.date_of_birth,
            "gender": active_grant.patient.gender,
        },
        "documents": [DocumentOut.model_validate(d).model_dump() for d in docs],
        "analysis": AIAnalysisOut.model_validate(analysis).model_dump() if analysis else None,
    }

