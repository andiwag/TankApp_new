"""User profile updates and password changes."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.models import User
from app.schemas import EMAIL_DUPLICATE_MESSAGE, PasswordChange, UserUpdate

_WRONG_CURRENT_PASSWORD = "Current password is incorrect"


def update_user_profile(db: Session, user: User, data: UserUpdate) -> str | None:
    """Apply profile fields. Returns an error message, or None on success."""
    if data.email is not None:
        normalized_email = data.email
        if normalized_email != user.email:
            other = (
                db.query(User)
                .filter(
                    User.email == normalized_email,
                    User.id != user.id,
                )
                .first()
            )
            if other:
                return EMAIL_DUPLICATE_MESSAGE
        user.email = normalized_email

    if data.name is not None:
        user.name = data.name

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return EMAIL_DUPLICATE_MESSAGE
    db.refresh(user)
    return None


def change_user_password(db: Session, user: User, data: PasswordChange) -> str | None:
    """Change password after verifying the current one. Returns error or None."""
    if not verify_password(data.current_password, user.password_hash):
        return _WRONG_CURRENT_PASSWORD

    user.password_hash = hash_password(data.new_password)
    db.commit()
    db.refresh(user)
    return None
