"""Server-side session storage for revocation support."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import SESSION_MAX_AGE
from app.models import UserSession


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def create_user_session(db: Session, user_id: int) -> str:
    session_id = str(uuid.uuid4())
    expires_at = _utcnow() + timedelta(seconds=SESSION_MAX_AGE)
    db.add(
        UserSession(
            id=session_id,
            user_id=user_id,
            expires_at=expires_at,
        )
    )
    db.flush()
    return session_id


def get_active_session(db: Session, session_id: str) -> UserSession | None:
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not session or session.revoked_at is not None:
        return None
    if session.expires_at is not None and _as_utc(session.expires_at) <= _utcnow():
        return None
    return session


def revoke_session(db: Session, session_id: str) -> None:
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if session and session.revoked_at is None:
        session.revoked_at = _utcnow()
        db.flush()


def revoke_all_user_sessions(
    db: Session, user_id: int, *, except_session_id: str | None = None
) -> None:
    now = _utcnow()
    query = db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.revoked_at == None,  # noqa: E711
    )
    if except_session_id:
        query = query.filter(UserSession.id != except_session_id)
    for session in query.all():
        session.revoked_at = now
    db.flush()


def list_active_sessions(db: Session, user_id: int) -> list[UserSession]:
    now = _utcnow()
    sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at == None,  # noqa: E711
        )
        .order_by(UserSession.created_at.desc())
        .all()
    )
    return [
        session
        for session in sessions
        if session.expires_at is not None and _as_utc(session.expires_at) > now
    ]


def start_user_session(
    response,
    db: Session,
    user_id: int,
    active_group_id: int | None = None,
) -> str:
    from app.auth import set_session_cookie

    session_id = create_user_session(db, user_id)
    db.commit()
    set_session_cookie(response, user_id, active_group_id, session_id=session_id)
    return session_id


def refresh_session_cookie(
    response,
    user_id: int,
    active_group_id: int | None,
    *,
    session_id: str,
) -> None:
    from app.auth import set_session_cookie

    set_session_cookie(response, user_id, active_group_id, session_id=session_id)
