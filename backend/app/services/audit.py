"""Audit logging helper service for recording security, consent, and access events."""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.consent import AuditLog, Notification


def log_audit_event(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: str,
    user_id: int | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Record an immutable-style audit log entry."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        details=details or {},
        ip_address=ip_address,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def send_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "consent",
) -> Notification:
    """Generate in-app notification for a user."""
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif
