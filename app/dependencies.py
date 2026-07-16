from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth import decode_session_cookie
from app.config import settings
from app.database import get_db
from app.enums import Role
from app.models import Group, User, UserGroup
from app.services.entitlements import effective_tier, tier_has_feature
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


class PlatformAdminRequiredException(Exception):
    pass


class EntitlementRequiredException(Exception):
    def __init__(self, feature: str):
        self.feature = feature


def is_platform_admin(user: User) -> bool:
    return user.email.lower() in settings.platform_admin_emails


def platform_view_is_valid(user: User, data: dict) -> bool:
    if not data.get("platform_view"):
        return False
    active_group_id = data.get("active_group_id")
    platform_view_group_id = data.get("platform_view_group_id")
    if not active_group_id or platform_view_group_id != active_group_id:
        return False
    return is_platform_admin(user)


def _session_data_without_platform_view(data: dict) -> dict:
    return {
        key: value
        for key, value in data.items()
        if key not in ("platform_view", "platform_view_group_id")
    }


def _attach_user_to_request(
    request: Request, db: Session, data: dict, user: User
) -> User:
    request.state.user = user
    request.state.platform_view = False

    active_group_id = data.get("active_group_id")
    platform_view_valid = platform_view_is_valid(user, data)
    session_data = data

    if data.get("platform_view") and not platform_view_valid:
        session_data = _session_data_without_platform_view(data)
        request.state.clear_invalid_platform_view = True

    request.state.session_data = session_data
    effective_active_group_id: int | None = None
    if active_group_id:
        group = db.query(Group).filter(Group.id == active_group_id).first()
        if group:
            membership = (
                db.query(UserGroup)
                .filter(
                    UserGroup.user_id == user.id,
                    UserGroup.group_id == group.id,
                )
                .first()
            )
            is_member = membership is not None
            if is_member or platform_view_valid:
                request.state.active_group = group
                tier = effective_tier(db, group.id)
                request.state.group_tier = tier
                request.state.can_maintenance = tier_has_feature(tier, "maintenance")
                request.state.can_analytics = tier_has_feature(tier, "analytics")
                effective_active_group_id = active_group_id
                if membership:
                    request.state.user_role = membership.role
                if platform_view_valid:
                    request.state.platform_view = True
                    request.state.platform_view_group = group
            else:
                request.state.clear_stale_active_group = True
        else:
            request.state.clear_stale_active_group = True

    if effective_active_group_id != active_group_id:
        request.state.session_data = {
            **session_data,
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


def require_platform_admin(
    user: User = Depends(get_current_user),
) -> User:
    if not is_platform_admin(user):
        raise PlatformAdminRequiredException()
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

        if (
            platform_view_is_valid(user, session_data)
            and session_data.get("platform_view_group_id") == active_group_id
        ):
            user_role_level = ROLE_HIERARCHY[Role.reader.value]
        else:
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


def require_entitlement(feature: str):
    from app.services.entitlements import effective_tier, tier_has_feature

    def _check(
        request: Request,
        db: Session = Depends(get_db),
        group: Group = Depends(get_active_group),
    ) -> Group:
        tier = effective_tier(db, group.id)
        if not tier_has_feature(tier, feature):
            raise EntitlementRequiredException(feature)
        return group

    return _check
