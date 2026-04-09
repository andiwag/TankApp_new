from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth import decode_session_cookie
from app.config import settings
from app.database import get_db
from app.enums import Role
from app.models import Group, User, UserGroup

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


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not cookie:
        raise NotAuthenticatedException()

    data = decode_session_cookie(cookie)
    if not data:
        raise NotAuthenticatedException()

    user = db.query(User).filter(
        User.id == data["user_id"],
        User.deleted_at == None,  # noqa: E711
    ).first()
    if not user:
        raise NotAuthenticatedException()

    request.state.session_data = data
    return user


def get_active_group(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Group:
    session_data = request.state.session_data
    active_group_id = session_data.get("active_group_id")
    if not active_group_id:
        raise NoActiveGroupException()

    group = db.query(Group).filter(
        Group.id == active_group_id,
        Group.deleted_at == None,  # noqa: E711
    ).first()
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

        user_group = db.query(UserGroup).filter(
            UserGroup.user_id == user.id,
            UserGroup.group_id == active_group_id,
        ).first()

        if not user_group:
            raise InsufficientRoleException()

        user_role_level = ROLE_HIERARCHY.get(user_group.role, 0)
        min_role_level = ROLE_HIERARCHY.get(min_role, 0)

        if user_role_level < min_role_level:
            raise InsufficientRoleException()

        return user

    return _check_role
