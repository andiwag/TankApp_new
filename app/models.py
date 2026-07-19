from datetime import date, datetime

from app.time_utils import utc_now


def _utcnow() -> datetime:
    return utc_now()


from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import (
    VTYPE_TO_USAGE_UNIT,
    FillSource,
    FuelType,
    Role,
    TankMovementType,
    UsageUnit,
    VehicleType,
)


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
    storage_tanks: Mapped[list["StorageTank"]] = relationship(back_populates="group")
    subscription: Mapped["GroupSubscription | None"] = relationship(
        back_populates="group", uselist=False
    )


class GroupSubscription(Base):
    __tablename__ = "group_subscriptions"

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    tier: Mapped[str] = mapped_column(String(16), default="free")
    current_period_end: Mapped[datetime | None] = mapped_column()
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    group: Mapped["Group"] = relationship(back_populates="subscription")


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stripe_event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    processed_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
        CheckConstraint(
            "adblue_amount_l IS NULL OR adblue_amount_l > 0",
            name="ck_adblue_amount_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    fuel_amount_l: Mapped[float] = mapped_column(Float)
    usage_reading: Mapped[float] = mapped_column(Float)
    full_tank: Mapped[bool] = mapped_column(Boolean, default=True)
    total_cost_eur: Mapped[float | None] = mapped_column(Float)
    adblue_amount_l: Mapped[float | None] = mapped_column(Float)
    fill_source: Mapped[str] = mapped_column(
        Enum(*[e.value for e in FillSource], name="fill_source_enum"),
        default=FillSource.external.value,
    )
    fuel_tank_id: Mapped[int | None] = mapped_column(ForeignKey("storage_tanks.id"))
    notes: Mapped[str | None] = mapped_column(String(500))
    entry_date: Mapped[date] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column()

    vehicle: Mapped["Vehicle"] = relationship(back_populates="fuel_entries")
    user: Mapped["User"] = relationship(back_populates="fuel_entries")
    fuel_tank: Mapped["StorageTank | None"] = relationship()
    tank_ledger_entries: Mapped[list["TankLedgerEntry"]] = relationship(
        back_populates="fuel_entry"
    )


class StorageTank(Base):
    __tablename__ = "storage_tanks"
    __table_args__ = (
        CheckConstraint("opening_balance_l >= 0", name="ck_tank_opening_non_negative"),
        CheckConstraint(
            "capacity_l IS NULL OR capacity_l > 0",
            name="ck_tank_capacity_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    name: Mapped[str] = mapped_column()
    fuel_type: Mapped[str] = mapped_column(
        Enum(*[e.value for e in FuelType], name="fuel_type_enum", create_type=False)
    )
    capacity_l: Mapped[float | None] = mapped_column(Float)
    opening_balance_l: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column()

    group: Mapped["Group"] = relationship(back_populates="storage_tanks")
    ledger_entries: Mapped[list["TankLedgerEntry"]] = relationship(
        back_populates="tank"
    )


class TankLedgerEntry(Base):
    __tablename__ = "tank_ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_l != 0", name="ck_ledger_amount_non_zero"),
        Index(
            "ix_tank_ledger_entries_fuel_entry_id",
            "fuel_entry_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tank_id: Mapped[int] = mapped_column(ForeignKey("storage_tanks.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    movement_type: Mapped[str] = mapped_column(
        Enum(
            *[e.value for e in TankMovementType],
            name="tank_movement_type_enum",
        )
    )
    amount_l: Mapped[float] = mapped_column(Float)
    entry_date: Mapped[date] = mapped_column()
    fuel_entry_id: Mapped[int | None] = mapped_column(ForeignKey("fuel_entries.id"))
    recipient_name: Mapped[str | None] = mapped_column(String(200))
    total_cost_eur: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column()

    tank: Mapped["StorageTank"] = relationship(back_populates="ledger_entries")
    fuel_entry: Mapped["FuelEntry | None"] = relationship(
        back_populates="tank_ledger_entries"
    )
    user: Mapped["User"] = relationship()


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
