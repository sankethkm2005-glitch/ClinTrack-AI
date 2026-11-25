"""Audit and Notification APIs."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.consent import Notification, AuditLog
from app.schemas.consent import NotificationOut, AuditLogOut
from app.utils.dependencies import get_current_user

router = APIRouter(tags=["Audit & Notifications"])


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve notifications for the authenticated user."""
    return (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a notification as read."""
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user.id,
    ).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"status": "success"}


@router.get("/audit/history", response_model=list[AuditLogOut])
def list_audit_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve audit history relevant to the authenticated user."""
    if user.role == "patient":
        # Audit logs relating to patient's record
        patient = user.patient_profile
        patient_id_str = str(patient.id) if patient else ""
        return (
            db.query(AuditLog)
            .filter(
                (AuditLog.user_id == user.id) |
                ((AuditLog.resource_type == "patient_record") & (AuditLog.resource_id == patient_id_str))
            )
            .order_by(AuditLog.created_at.desc())
            .limit(100)
            .all()
        )
    else:
        # Audit logs initiated by the doctor
        return (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user.id)
            .order_by(AuditLog.created_at.desc())
            .limit(100)
            .all()
        )
