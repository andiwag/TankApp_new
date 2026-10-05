from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth import decode_session_cookie
from app.config import settings
from app.database import get_db
from app.enums import Role
from app.models import Group, User, UserGroup
from app.services.entitlements import effective_tier, tier_has_feature
from app.services.sessions import get_active_session, slide_session_expiry

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


def _live_group(db: Session, group_id: int) -> Group | None:
    return (
        db.query(Group)
        .filter(
            Group.id == group_id,
            Group.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def _membership(db: Session, user_id: int, group_id: int) -> UserGroup | None:
    return (
        db.query(UserGroup)
        .filter(
            UserGroup.user_id == user_id,
            UserGroup.group_id == group_id,
        )
        .first()
    )


def _bind_group(
    request: Request,
    db: Session,
    group: Group,
    membership: UserGroup | None,
    *,
    platform_view: bool,
) -> None:
    request.state.active_group = group
    tier = effective_tier(db, group.id)
    request.state.group_tier = tier
    request.state.can_maintenance = tier_has_feature(tier, "maintenance")
    request.state.can_analytics = tier_has_feature(tier, "analytics")
    if membership is not None:
        request.state.user_role = membership.role
    if platform_view:
        request.state.platform_view = True
        request.state.platform_view_group = group


def _attach_user_to_request(
    request: Request, db: Session, data: dict, user: User
) -> User:
    from app.services.groups import default_group_for_user, remember_last_group

    request.state.user = user
    request.state.platform_view = False

    active_group_id = data.get("active_group_id")
    platform_view_valid = platform_view_is_valid(user, data)
    session_data = data

    if data.get("platform_view") and not platform_view_valid:
        session_data = _session_data_without_platform_view(data)
        request.state.clear_invalid_platform_view = True

    request.state.session_data = session_data

    group: Group | None = None
    membership: UserGroup | None = None
    opened_platform_view = False
    if active_group_id:
        group = _live_group(db, active_group_id)
        membership = (
            _membership(db, user.id, active_group_id) if group is not None else None
        )
        if group is not None and (membership is not None or platform_view_valid):
            opened_platform_view = platform_view_valid
        else:
            group = None
            membership = None

    if group is None:
        fallback = default_group_for_user(db, user)
        if fallback is not None:
            group = fallback
            membership = _membership(db, user.id, fallback.id)
            request.state.persist_active_group = True
        elif active_group_id:
            request.state.clear_stale_active_group = True

    if group is not None:
        _bind_group(
            request,
            db,
            group,
            membership,
            platform_view=opened_platform_view,
        )
        if not opened_platform_view:
            # Support view must not become the farm opened on the next login.
            remember_last_group(db, user, group.id)

    effective_active_group_id = group.id if group is not None else None
    if effective_active_group_id != active_group_id:
        request.state.session_data = {
            **request.state.session_data,
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

    slide_session_expiry(db, session)
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
