from datetime import UTC, date, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


from sqlalchemy import Boolean, CheckConstraint, Enum, Float, ForeignKey, String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import VTYPE_TO_USAGE_UNIT, FuelType, Role, UsageUnit, VehicleType


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column()
    password_hash: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column()

    user_groups: Mapped[list["UserGroup"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    fuel_entries: Mapped[list["FuelEntry"]] = relationship(back_populates="user")
    maintenance_logs: Mapped[list["MaintenanceLog"]] = relationship(
        back_populates="user"
    )
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column()
    invite_code: Mapped[str] = mapped_column(unique=True)
    subscription_tier: Mapped[str | None] = mapped_column()
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column()

    user_groups: Mapped[list["UserGroup"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="group")


class UserGroup(Base):
    __tablename__ = "user_groups"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
    role: Mapped[str] = mapped_column(Enum(*[e.value for e in Role], name="role_enum"))
    joined_at: Mapped[datetime] = mapped_column(default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="user_groups")
    group: Mapped["Group"] = relationship(back_populates="user_groups")


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    name: Mapped[str] = mapped_column()
    vtype: Mapped[str] = mapped_column(
        Enum(*[e.value for e in VehicleType], name="vtype_enum")
    )
    usage_unit: Mapped[str] = mapped_column(
        Enum(*[e.value for e in UsageUnit], name="usage_unit_enum")
    )
    fuel_type: Mapped[str] = mapped_column(
        Enum(*[e.value for e in FuelType], name="fuel_type_enum")
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column()

    group: Mapped["Group"] = relationship(back_populates="vehicles")
    fuel_entries: Mapped[list["FuelEntry"]] = relationship(back_populates="vehicle")
    maintenance_logs: Mapped[list["MaintenanceLog"]] = relationship(
        back_populates="vehicle"
    )


@event.listens_for(Vehicle, "init")
def _set_usage_unit(target: Vehicle, args: tuple, kwargs: dict) -> None:
    vtype = kwargs.get("vtype")
    if vtype and "usage_unit" not in kwargs:
        kwargs["usage_unit"] = VTYPE_TO_USAGE_UNIT[vtype]


class FuelEntry(Base):
    __tablename__ = "fuel_entries"
    __table_args__ = (
        CheckConstraint("fuel_amount_l > 0", name="ck_fuel_amount_positive"),
        CheckConstraint("usage_reading >= 0", name="ck_usage_reading_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    fuel_amount_l: Mapped[float] = mapped_column(Float)
    usage_reading: Mapped[float] = mapped_column(Float)
    full_tank: Mapped[bool] = mapped_column(Boolean, default=True)
    total_cost_eur: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(String(500))
    entry_date: Mapped[date] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column()

    vehicle: Mapped["Vehicle"] = relationship(back_populates="fuel_entries")
    user: Mapped["User"] = relationship(back_populates="fuel_entries")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column()
    entity_type: Mapped[str] = mapped_column()
    entity_id: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    user: Mapped["User"] = relationship()


class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"
    __table_args__ = (
        CheckConstraint(
            "usage_reading IS NULL OR usage_reading >= 0",
            name="ck_maint_usage_non_negative",
        ),
        CheckConstraint(
            "cost_eur IS NULL OR cost_eur >= 0", name="ck_maint_cost_non_negative"
        ),
        CheckConstraint(
            "next_service_usage IS NULL OR next_service_usage >= 0",
            name="ck_maint_next_usage_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    service_date: Mapped[date] = mapped_column()
    usage_reading: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String(500))
    cost_eur: Mapped[float | None] = mapped_column(Float)
    next_service_date: Mapped[date | None] = mapped_column()
    next_service_usage: Mapped[float | None] = mapped_column(Float)
    reminder_sent_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column()

    vehicle: Mapped["Vehicle"] = relationship(back_populates="maintenance_logs")
    user: Mapped["User"] = relationship(back_populates="maintenance_logs")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column()

    user: Mapped["User"] = relationship(back_populates="sessions")
