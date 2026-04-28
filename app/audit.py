"""Audit logging helper for significant structural events."""

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_event(
    db: Session,
    group_id: int | None,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: int,
) -> AuditLog:
    audit_log = AuditLog(
        group_id=group_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(audit_log)
    db.flush()
    return audit_log
