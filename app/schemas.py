from datetime import date
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    EmailStr,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.enums import FuelType, VehicleType

MIN_PASSWORD_LENGTH = 8

# Shown when another account already holds this email (registration or profile update).
EMAIL_DUPLICATE_MESSAGE = "E-Mail wird bereits verwendet"
INVITE_CODE_INVALID_MESSAGE = "Ungültiger Einladungscode"


# ── Validation helpers ───────────────────────────────────────────────────────


def first_validation_error_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Ungültige Eingabe"
    msg = errors[0]["msg"]
    prefix = "Value error, "
    if msg.startswith(prefix):
        msg = msg[len(prefix) :]
    return msg


# ── Reusable annotated types ─────────────────────────────────────────────────


def _strip_and_require(v: str) -> str:
    stripped = v.strip()
    if not stripped:
        raise ValueError("Name darf nicht leer sein")
    return stripped


NonEmptyStr = Annotated[str, AfterValidator(_strip_and_require)]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _validate_password_match(password: str, confirm: str) -> None:
    if password != confirm:
        raise ValueError("Passwörter stimmen nicht überein")


def _validate_password_length(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben")


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
    name: str | None = None
    email: EmailStr | None = None

    @field_validator("name")
    @classmethod
    def name_non_empty_if_set(cls, v: object) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            return v  # type: ignore[return-value]
        return _strip_and_require(v)

    @field_validator("email", mode="before")
    @classmethod
    def email_strip_whitespace(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            return v.lower()
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdate":
        if self.name is None and self.email is None:
            raise ValueError("Mindestens Name oder E-Mail muss angegeben werden")
        return self


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
    name: str | None = None
    fuel_type: FuelType | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_optional_name(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "VehicleUpdate":
        if self.name is None and self.fuel_type is None:
            raise ValueError("Mindestens Name oder Kraftstofftyp muss angegeben werden")
        return self


# ── FuelEntry schemas ────────────────────────────────────────────────────────


class FuelEntryCreate(BaseModel):
    vehicle_id: int
    fuel_amount_l: float = Field(gt=0)
    usage_reading: float = Field(ge=0)
    entry_date: date
    full_tank: bool = True
    total_cost_eur: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_date_not_future(self) -> "FuelEntryCreate":
        if self.entry_date > date.today():
            raise ValueError("Datum darf nicht in der Zukunft liegen")
        return self


class FuelEntryUpdate(BaseModel):
    fuel_amount_l: float | None = Field(default=None, gt=0)
    usage_reading: float | None = Field(default=None, ge=0)
    entry_date: date | None = None
    full_tank: bool | None = None
    total_cost_eur: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "FuelEntryUpdate":
        if (
            self.fuel_amount_l is None
            and self.usage_reading is None
            and self.entry_date is None
            and self.full_tank is None
            and self.total_cost_eur is None
            and self.notes is None
        ):
            raise ValueError("Mindestens ein Feld muss angegeben werden")
        return self

    @model_validator(mode="after")
    def validate_date_not_future(self) -> "FuelEntryUpdate":
        if self.entry_date is not None and self.entry_date > date.today():
            raise ValueError("Datum darf nicht in der Zukunft liegen")
        return self


# ── Group schemas ────────────────────────────────────────────────────────────


class GroupCreate(BaseModel):
    name: NonEmptyStr


class JoinGroup(BaseModel):
    invite_code: str


# ── Maintenance log schemas ─────────────────────────────────────────────────


class MaintenanceLogCreate(BaseModel):
    vehicle_id: int
    service_date: date
    usage_reading: float | None = Field(default=None, ge=0)
    description: str = Field(min_length=1, max_length=500)
    cost_eur: float | None = Field(default=None, ge=0)
    next_service_date: date | None = None
    next_service_usage: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_dates(self) -> "MaintenanceLogCreate":
        if self.service_date > date.today():
            raise ValueError("Servicedatum darf nicht in der Zukunft liegen")
        if (
            self.next_service_date is not None
            and self.next_service_date < self.service_date
        ):
            raise ValueError(
                "Nächstes Servicedatum muss am oder nach dem Servicedatum liegen"
            )
        return self


class MaintenanceLogUpdate(BaseModel):
    service_date: date | None = None
    usage_reading: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    cost_eur: float | None = Field(default=None, ge=0)
    next_service_date: date | None = None
    next_service_usage: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "MaintenanceLogUpdate":
        if (
            self.service_date is None
            and self.usage_reading is None
            and self.description is None
            and self.cost_eur is None
            and self.next_service_date is None
            and self.next_service_usage is None
        ):
            raise ValueError("Mindestens ein Feld muss angegeben werden")
        return self

    @model_validator(mode="after")
    def validate_dates(self) -> "MaintenanceLogUpdate":
        if self.service_date is not None and self.service_date > date.today():
            raise ValueError("Servicedatum darf nicht in der Zukunft liegen")
        return self
