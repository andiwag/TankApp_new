from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth import decode_session_cookie
from app.config import settings
from app.database import get_db
from app.enums import Role
from app.models import Group, User, UserGroup
from app.services.sessions import get_active_session

ROLE_HIERARCHY: dict[str, int] = {
    Role.admin.value: 3,
    Role.contributor.value: 2,
    Role.reader.value: 1,
}


class NotAuthenticatedException(Exception):
    pass


class NoActiveGroupException(Exception):
    pass


class InsufficientRoleException(Exception):
    pass


def _attach_user_to_request(
    request: Request, db: Session, data: dict, user: User
) -> User:
    request.state.session_data = data
    request.state.user = user

    active_group_id = data.get("active_group_id")
    effective_active_group_id: int | None = None
    if active_group_id:
        group = (
            db.query(Group)
            .filter(
                Group.id == active_group_id,
                Group.deleted_at == None,  # noqa: E711
            )
            .first()
        )
        if group:
            is_member = (
                db.query(UserGroup)
                .filter(
                    UserGroup.user_id == user.id,
                    UserGroup.group_id == group.id,
                )
                .first()
                is not None
            )
            if is_member:
                request.state.active_group = group
                effective_active_group_id = active_group_id
            else:
                request.state.clear_stale_active_group = True
        else:
            request.state.clear_stale_active_group = True

    if effective_active_group_id != active_group_id:
        request.state.session_data = {
            **data,
            "active_group_id": effective_active_group_id,
        }

    return user


def _resolve_user_from_request(request: Request, db: Session) -> User | None:
    cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not cookie:
        return None

    data = decode_session_cookie(cookie)
    if not data:
        return None

    session_id = data.get("session_id")
    session = get_active_session(db, session_id) if session_id else None
    if not session:
        return None

    if session.user_id != data.get("user_id"):
        return None

    user = (
        db.query(User)
        .filter(
            User.id == session.user_id,
            User.deleted_at == None,  # noqa: E711
        )
        .first()
    )
    if not user:
        return None

    return _attach_user_to_request(request, db, data, user)


def get_optional_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    return _resolve_user_from_request(request, db)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _resolve_user_from_request(request, db)
    if not user:
        raise NotAuthenticatedException()
    return user


def get_active_group(
    request: Request,
    user: User = Depends(get_current_user),
) -> Group:
    group = request.state.active_group
    if not group:
        raise NoActiveGroupException()
    return group


def require_role(min_role: str):
    def _check_role(
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> User:
        session_data = request.state.session_data
        active_group_id = session_data.get("active_group_id")
        if not active_group_id:
            raise NoActiveGroupException()

        user_group = (
            db.query(UserGroup)
            .filter(
                UserGroup.user_id == user.id,
                UserGroup.group_id == active_group_id,
            )
            .first()
        )

        if not user_group:
            raise InsufficientRoleException()

        user_role_level = ROLE_HIERARCHY.get(user_group.role, 0)
        min_role_level = ROLE_HIERARCHY.get(min_role, 0)

        if user_role_level < min_role_level:
            raise InsufficientRoleException()

        return user

    return _check_role
