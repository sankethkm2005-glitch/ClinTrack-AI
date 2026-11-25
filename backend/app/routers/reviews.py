"""Doctor review router for findings and clinical decision-support."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.analysis import AIFinding
from app.models.consent import FindingReview, AccessGrant
from app.schemas.consent import FindingReviewCreate, FindingReviewOut
from app.utils.dependencies import require_doctor
from app.services.audit import log_audit_event

router = APIRouter(prefix="/reviews", tags=["Doctor Review"])


def _is_grant_active(grant: AccessGrant) -> bool:
    if grant.revoked_at is not None:
        return False
    exp = grant.expires_at
    now = datetime.now(timezone.utc)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > now



def _check_doctor_grant_for_finding(db: Session, doctor_id: int, finding_id: int) -> AIFinding:
    """Verifies that doctor has active access grant to review findings of this patient."""
    finding = db.query(AIFinding).filter(AIFinding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Clinical finding not found.")

    patient_id = finding.analysis.patient_id
    matching_grants = (
        db.query(AccessGrant)
        .filter(
            AccessGrant.doctor_id == doctor_id,
            AccessGrant.patient_id == patient_id,
            AccessGrant.revoked_at == None,
        )
        .all()
    )
    grant = next((g for g in matching_grants if _is_grant_active(g)), None)
    if not grant:
        raise HTTPException(
            status_code=403,
            detail="Doctor does not have an active consent grant for this patient's records.",
        )
    return finding


@router.post("/findings/{finding_id}", response_model=FindingReviewOut, status_code=status.HTTP_201_CREATED)
def submit_finding_review(
    finding_id: int,
    payload: FindingReviewCreate,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    """
    Submit a doctor review (accept, reject, clarification, resolve).
    Stored in a dedicated table separate from the AI findings.
    """
    finding = _check_doctor_grant_for_finding(db, doctor.id, finding_id)

    review = FindingReview(
        finding_id=finding.id,
        doctor_id=doctor.id,
        action=payload.action,
        explanation=payload.explanation.strip(),
    )
    db.add(review)

    # Update finding review status tag
    status_map = {
        "accept": "reviewed",
        "reject": "reviewed",
        "clarification": "clarification_requested",
        "resolve": "resolved",
    }
    finding.review_status = status_map.get(payload.action, "reviewed")

    db.commit()
    db.refresh(review)

    log_audit_event(
        db=db,
        action="finding_reviewed",
        resource_type="ai_finding",
        resource_id=str(finding.id),
        user_id=doctor.id,
        details={"action": payload.action, "explanation": payload.explanation},
    )

    doc_name = doctor.doctor_profile.full_name if doctor.doctor_profile else "Doctor"
    return FindingReviewOut(
        id=review.id,
        finding_id=review.finding_id,
        doctor_id=review.doctor_id,
        doctor_name=doc_name,
        action=review.action,
        explanation=review.explanation,
        created_at=review.created_at,
    )


@router.get("/findings/{finding_id}", response_model=list[FindingReviewOut])
def get_finding_reviews(
    finding_id: int,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    """List historical reviews for a specific AI finding."""
    _check_doctor_grant_for_finding(db, doctor.id, finding_id)
    reviews = (
        db.query(FindingReview)
        .filter(FindingReview.finding_id == finding_id)
        .order_by(FindingReview.created_at.desc())
        .all()
    )
    results = []
    for r in reviews:
        doc_name = r.doctor.doctor_profile.full_name if r.doctor and r.doctor.doctor_profile else "Doctor"
        results.append(
            FindingReviewOut(
                id=r.id,
                finding_id=r.finding_id,
                doctor_id=r.doctor_id,
                doctor_name=doc_name,
                action=r.action,
                explanation=r.explanation,
                created_at=r.created_at,
            )
        )
    return results
