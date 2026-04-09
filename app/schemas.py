from datetime import date
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, EmailStr, Field, model_validator

from app.enums import FuelType, VehicleType


MIN_PASSWORD_LENGTH = 8


# ── Reusable annotated types ─────────────────────────────────────────────────


def _strip_and_require(v: str) -> str:
    stripped = v.strip()
    if not stripped:
        raise ValueError("Name must not be empty")
    return stripped


NonEmptyStr = Annotated[str, AfterValidator(_strip_and_require)]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _validate_password_match(password: str, confirm: str) -> None:
    if password != confirm:
        raise ValueError("Passwords do not match")


def _validate_password_length(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )


# ── User schemas ─────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    email: EmailStr
    name: NonEmptyStr
    password: str
    password_confirm: str

    @model_validator(mode="after")
    def validate_passwords(self) -> "UserCreate":
        _validate_password_length(self.password)
        _validate_password_match(self.password, self.password_confirm)
        return self


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str

    @model_validator(mode="after")
    def validate_passwords(self) -> "PasswordChange":
        _validate_password_length(self.new_password)
        _validate_password_match(self.new_password, self.new_password_confirm)
        return self


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
    new_password_confirm: str

    @model_validator(mode="after")
    def validate_passwords(self) -> "PasswordResetConfirm":
        _validate_password_length(self.new_password)
        _validate_password_match(self.new_password, self.new_password_confirm)
        return self


# ── Vehicle schemas ──────────────────────────────────────────────────────────


class VehicleCreate(BaseModel):
    name: NonEmptyStr
    vtype: VehicleType
    fuel_type: FuelType


class VehicleUpdate(BaseModel):
    name: Optional[str] = None
    fuel_type: Optional[FuelType] = None


# ── FuelEntry schemas ────────────────────────────────────────────────────────


class FuelEntryCreate(BaseModel):
    vehicle_id: int
    fuel_amount_l: float = Field(gt=0)
    usage_reading: float = Field(ge=0)
    entry_date: date
    notes: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_date_not_future(self) -> "FuelEntryCreate":
        if self.entry_date > date.today():
            raise ValueError("entry_date must not be in the future")
        return self


class FuelEntryUpdate(BaseModel):
    fuel_amount_l: Optional[float] = Field(default=None, gt=0)
    usage_reading: Optional[float] = Field(default=None, ge=0)
    entry_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=500)


# ── Group schemas ────────────────────────────────────────────────────────────


class GroupCreate(BaseModel):
    name: NonEmptyStr


class JoinGroup(BaseModel):
    invite_code: str
