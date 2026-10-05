"""Server-side session storage for revocation support."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import (
    SESSION_ABSOLUTE_MAX_AGE,
    SESSION_IDLE_MAX_AGE,
    SESSION_SLIDE_INTERVAL,
)
from app.models import UserSession
from app.time_utils import UTC, utc_now


def _utcnow() -> datetime:
    return utc_now()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _absolute_end(session: UserSession) -> datetime:
    return _as_utc(session.created_at) + timedelta(seconds=SESSION_ABSOLUTE_MAX_AGE)


def _is_live(session: UserSession, now: datetime) -> bool:
    if session.revoked_at is not None or session.expires_at is None:
        return False
    if _as_utc(session.expires_at) <= now or _absolute_end(session) <= now:
        return False
    return True


def _next_expiry(session: UserSession, now: datetime) -> datetime | None:
    absolute_end = _absolute_end(session)
    if now >= absolute_end:
        return None
    return min(now + timedelta(seconds=SESSION_IDLE_MAX_AGE), absolute_end)


def create_user_session(db: Session, user_id: int) -> str:
    session_id = str(uuid.uuid4())
    expires_at = _utcnow() + timedelta(seconds=SESSION_IDLE_MAX_AGE)
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
    if not session or not _is_live(session, _utcnow()):
        return None
    return session


def slide_session_expiry(db: Session, session: UserSession) -> bool:
    """Extend the idle deadline. Writes at most once per slide interval."""
    now = _utcnow()
    new_expiry = _next_expiry(session, now)
    if new_expiry is None:
        return False
    if new_expiry - _as_utc(session.expires_at) < timedelta(
        seconds=SESSION_SLIDE_INTERVAL
    ):
        return False
    session.expires_at = new_expiry
    db.commit()
    return True


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
    return [session for session in sessions if _is_live(session, now)]


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
    platform_view: bool = False,
    platform_view_group_id: int | None = None,
) -> None:
    from app.auth import set_session_cookie

    set_session_cookie(
        response,
        user_id,
        active_group_id,
        session_id=session_id,
        platform_view=platform_view,
        platform_view_group_id=platform_view_group_id,
    )
