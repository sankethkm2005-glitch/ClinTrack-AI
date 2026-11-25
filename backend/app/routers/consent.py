"""Consent management router: requests, approvals, revocations, and emergency access."""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, PatientProfile, DoctorProfile
from app.models.consent import AccessRequest, AccessGrant
from app.schemas.consent import (
    AccessRequestCreate,
    EmergencyAccessCreate,
    AccessRequestAction,
    AccessRequestOut,
    AccessGrantOut,
)
from app.utils.dependencies import get_current_user, require_doctor, require_patient
from app.services.audit import log_audit_event, send_notification

router = APIRouter(prefix="/consent", tags=["Consent & Access Management"])


def _is_grant_active(grant: AccessGrant) -> bool:
    """Helper to check if an access grant is currently active regardless of tz offset."""
    if grant.revoked_at is not None:
        return False
    exp = grant.expires_at
    now = datetime.now(timezone.utc)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > now



@router.post("/requests", response_model=AccessRequestOut, status_code=status.HTTP_201_CREATED)
def request_patient_access(
    payload: AccessRequestCreate,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    """Allows an authenticated doctor to submit an access request specifying a clinical reason."""
    patient = (
        db.query(PatientProfile)
        .filter(PatientProfile.patient_id == payload.patient_id_str.strip())
        .first()
    )
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient ID '{payload.patient_id_str}' not found.",
        )

    # Check for active existing grant
    now = datetime.now(timezone.utc)
    active_grant = (
        db.query(AccessGrant)
        .filter(
            AccessGrant.doctor_id == doctor.id,
            AccessGrant.patient_id == patient.id,
            AccessGrant.expires_at > now,
            AccessGrant.revoked_at == None,
        )
        .first()
    )
    if active_grant:
        raise HTTPException(
            status_code=400,
            detail="You already have an active access grant for this patient's records.",
        )

    # Create pending access request
    req = AccessRequest(
        doctor_id=doctor.id,
        patient_id=patient.id,
        reason=payload.reason.strip(),
        is_emergency=False,
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Audit & Notify
    log_audit_event(
        db=db,
        action="access_requested",
        resource_type="patient_record",
        resource_id=str(patient.id),
        user_id=doctor.id,
        details={"reason": payload.reason, "patient_id_str": patient.patient_id},
    )

    doc_name = doctor.doctor_profile.full_name if doctor.doctor_profile else "A doctor"
    send_notification(
        db=db,
        user_id=patient.user_id,
        title="New Access Request Received",
        message=f"{doc_name} has requested access to your medical records. Reason: '{payload.reason}'",
        notification_type="consent",
    )

    return AccessRequestOut(
        id=req.id,
        doctor_id=doctor.id,
        doctor_name=doctor.doctor_profile.full_name if doctor.doctor_profile else "Doctor",
        doctor_specialization=doctor.doctor_profile.specialization if doctor.doctor_profile else None,
        patient_id=patient.id,
        patient_id_str=patient.patient_id,
        patient_name=patient.full_name,
        reason=req.reason,
        is_emergency=req.is_emergency,
        status=req.status,
        created_at=req.created_at,
    )


@router.get("/requests", response_model=list[AccessRequestOut])
def list_access_requests(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List access requests for either the patient or doctor."""
    if user.role == "patient":
        patient = user.patient_profile
        if not patient:
            return []
        query = db.query(AccessRequest).filter(AccessRequest.patient_id == patient.id)
    else:
        query = db.query(AccessRequest).filter(AccessRequest.doctor_id == user.id)

    requests = query.order_by(AccessRequest.created_at.desc()).all()
    results = []
    for r in requests:
        results.append(
            AccessRequestOut(
                id=r.id,
                doctor_id=r.doctor_id,
                doctor_name=r.doctor.doctor_profile.full_name if r.doctor and r.doctor.doctor_profile else "Doctor",
                doctor_specialization=r.doctor.doctor_profile.specialization if r.doctor and r.doctor.doctor_profile else None,
                patient_id=r.patient_id,
                patient_id_str=r.patient.patient_id if r.patient else None,
                patient_name=r.patient.full_name if r.patient else None,
                reason=r.reason,
                is_emergency=r.is_emergency,
                status=r.status,
                created_at=r.created_at,
            )
        )
    return results


@router.patch("/requests/{request_id}", response_model=AccessRequestOut)
def respond_to_access_request(
    request_id: int,
    payload: AccessRequestAction,
    patient_user: User = Depends(require_patient),
    db: Session = Depends(get_db),
):
    """Allows patient to approve or reject a pending request."""
    patient = patient_user.patient_profile
    req = db.query(AccessRequest).filter(
        AccessRequest.id == request_id,
        AccessRequest.patient_id == patient.id,
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Access request not found.")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request has already been {req.status}.")

    now = datetime.now(timezone.utc)
    if payload.action == "approve":
        req.status = "approved"
        grant = AccessGrant(
            doctor_id=req.doctor_id,
            patient_id=patient.id,
            request_id=req.id,
            scope="full_records",
            is_emergency=False,
            expires_at=now + timedelta(hours=payload.duration_hours),
        )
        db.add(grant)

        log_audit_event(
            db=db,
            action="access_granted",
            resource_type="patient_record",
            resource_id=str(patient.id),
            user_id=patient_user.id,
            details={"duration_hours": payload.duration_hours, "doctor_id": req.doctor_id},
        )
        send_notification(
            db=db,
            user_id=req.doctor_id,
            title="Access Request Approved",
            message=f"Patient {patient.full_name} ({patient.patient_id}) approved your access request for {payload.duration_hours} hours.",
            notification_type="consent",
        )
    else:
        req.status = "rejected"
        log_audit_event(
            db=db,
            action="access_rejected",
            resource_type="patient_record",
            resource_id=str(patient.id),
            user_id=patient_user.id,
            details={"doctor_id": req.doctor_id},
        )
        send_notification(
            db=db,
            user_id=req.doctor_id,
            title="Access Request Rejected",
            message=f"Patient {patient.full_name} declined your access request.",
            notification_type="consent",
        )

    db.commit()
    db.refresh(req)

    return AccessRequestOut(
        id=req.id,
        doctor_id=req.doctor_id,
        doctor_name=req.doctor.doctor_profile.full_name if req.doctor and req.doctor.doctor_profile else "Doctor",
        doctor_specialization=req.doctor.doctor_profile.specialization if req.doctor and req.doctor.doctor_profile else None,
        patient_id=patient.id,
        patient_id_str=patient.patient_id,
        patient_name=patient.full_name,
        reason=req.reason,
        is_emergency=req.is_emergency,
        status=req.status,
        created_at=req.created_at,
    )


@router.get("/grants", response_model=list[AccessGrantOut])
def list_access_grants(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active and historical access grants."""
    now = datetime.now(timezone.utc)
    if user.role == "patient":
        patient = user.patient_profile
        if not patient:
            return []
        query = db.query(AccessGrant).filter(AccessGrant.patient_id == patient.id)
    else:
        query = db.query(AccessGrant).filter(AccessGrant.doctor_id == user.id)

    grants = query.order_by(AccessGrant.created_at.desc()).all()
    results = []
    for g in grants:
        is_active = _is_grant_active(g)
        results.append(
            AccessGrantOut(
                id=g.id,
                doctor_id=g.doctor_id,
                doctor_name=g.doctor.doctor_profile.full_name if g.doctor and g.doctor.doctor_profile else "Doctor",
                patient_id=g.patient_id,
                patient_id_str=g.patient.patient_id if g.patient else None,
                patient_name=g.patient.full_name if g.patient else None,
                scope=g.scope,
                is_emergency=g.is_emergency,
                is_active=is_active,
                expires_at=g.expires_at,
                revoked_at=g.revoked_at,
                created_at=g.created_at,
            )
        )
    return results


@router.delete("/grants/{grant_id}")
def revoke_access_grant(
    grant_id: int,
    patient_user: User = Depends(require_patient),
    db: Session = Depends(get_db),
):
    """Allows patient to revoke an access grant immediately."""
    patient = patient_user.patient_profile
    grant = db.query(AccessGrant).filter(
        AccessGrant.id == grant_id,
        AccessGrant.patient_id == patient.id,
    ).first()

    if not grant:
        raise HTTPException(status_code=404, detail="Access grant not found.")
    if grant.revoked_at:
        raise HTTPException(status_code=400, detail="Grant has already been revoked.")

    now = datetime.now(timezone.utc)
    grant.revoked_at = now
    db.commit()

    log_audit_event(
        db=db,
        action="access_revoked",
        resource_type="patient_record",
        resource_id=str(patient.id),
        user_id=patient_user.id,
        details={"grant_id": grant.id, "doctor_id": grant.doctor_id},
    )
    send_notification(
        db=db,
        user_id=grant.doctor_id,
        title="Access Revoked by Patient",
        message=f"Access to {patient.full_name}'s records has been revoked.",
        notification_type="consent",
    )
    return {"status": "success", "message": "Access grant revoked successfully."}


@router.post("/emergency-access", response_model=AccessGrantOut)
def initiate_emergency_access(
    payload: EmergencyAccessCreate,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    """
    Restricted, audited emergency access workflow.
    Requires an explicit mandatory justification, creates an immediate time-limited grant,
    logs the event in audit logs, and notifies the patient.
    """
    patient = (
        db.query(PatientProfile)
        .filter(PatientProfile.patient_id == payload.patient_id_str.strip())
        .first()
    )
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID '{payload.patient_id_str}' not found.",
        )

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=4)  # Emergency grants are restricted to 4 hours

    grant = AccessGrant(
        doctor_id=doctor.id,
        patient_id=patient.id,
        request_id=None,
        scope="emergency_clinical_review",
        is_emergency=True,
        expires_at=expires,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)

    # Audited as critical emergency override event
    log_audit_event(
        db=db,
        action="emergency_access_invoked",
        resource_type="patient_record",
        resource_id=str(patient.id),
        user_id=doctor.id,
        details={
            "justification": payload.reason,
            "patient_id_str": patient.patient_id,
            "grant_id": grant.id,
            "duration_hours": 4,
        },
    )

    doc_name = doctor.doctor_profile.full_name if doctor.doctor_profile else "A clinician"
    send_notification(
        db=db,
        user_id=patient.user_id,
        title="EMERGENCY ACCESS INVOKED",
        message=(
            f"Emergency access was invoked for your medical records by {doc_name}. "
            f"Mandatory reason provided: '{payload.reason}'. Event recorded in audit history."
        ),
        notification_type="emergency",
    )

    return AccessGrantOut(
        id=grant.id,
        doctor_id=doctor.id,
        doctor_name=doctor.doctor_profile.full_name if doctor.doctor_profile else "Doctor",
        patient_id=patient.id,
        patient_id_str=patient.patient_id,
        patient_name=patient.full_name,
        scope=grant.scope,
        is_emergency=True,
        is_active=True,
        expires_at=grant.expires_at,
        revoked_at=None,
        created_at=grant.created_at,
    )
