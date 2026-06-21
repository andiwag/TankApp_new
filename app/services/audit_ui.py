"""Audit log queries for the admin UI."""

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def list_audit_logs_for_group(
    db: Session,
    group_id: int,
    *,
    limit: int = 100,
) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.group_id == group_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )


def audit_log_page_context(db: Session, group_id: int) -> dict:
    logs = list_audit_logs_for_group(db, group_id)
    user_names = {
        u.id: u.name
        for u in db.query(User).filter(
            User.id.in_({log.user_id for log in logs} or {0})
        )
    }
    rows = [
        {
            "id": log.id,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "user_name": user_names.get(log.user_id, "Unknown"),
            "created_at": log.created_at,
        }
        for log in logs
    ]
    return {"audit_rows": rows, "show_empty_state": len(rows) == 0}
