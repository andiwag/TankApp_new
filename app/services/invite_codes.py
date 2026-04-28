"""Invite-code generation shared by group creation and settings."""

import secrets
import string

from sqlalchemy.orm import Session

from app.models import Group

_INVITE_CODE_CHARS = string.ascii_uppercase + string.digits
_INVITE_CODE_LENGTH = 5
_INVITE_CODE_PREFIX = "FARM-"
_MAX_INVITE_CODE_RETRIES = 10


class InviteCodeGenerationError(Exception):
    pass


def generate_invite_code() -> str:
    suffix = "".join(
        secrets.choice(_INVITE_CODE_CHARS) for _ in range(_INVITE_CODE_LENGTH)
    )
    return f"{_INVITE_CODE_PREFIX}{suffix}"


def generate_unique_invite_code(db: Session) -> str:
    for _ in range(_MAX_INVITE_CODE_RETRIES):
        code = generate_invite_code()
        existing = db.query(Group).filter(Group.invite_code == code).first()
        if not existing:
            return code
    raise InviteCodeGenerationError("Failed to generate unique invite code")
