from enum import StrEnum


class VehicleType(StrEnum):
    car = "car"
    motorcycle = "motorcycle"
    tractor = "tractor"
    machine = "machine"


class FuelType(StrEnum):
    diesel = "diesel"
    petrol = "petrol"


class Role(StrEnum):
    admin = "admin"
    contributor = "contributor"
    reader = "reader"


class UsageUnit(StrEnum):
    km = "km"
    hours = "hours"


VTYPE_TO_USAGE_UNIT: dict[VehicleType, UsageUnit] = {
    VehicleType.car: UsageUnit.km,
    VehicleType.motorcycle: UsageUnit.km,
    VehicleType.tractor: UsageUnit.hours,
    VehicleType.machine: UsageUnit.hours,
}


class FillSource(StrEnum):
    external = "external"
    farm = "farm"


class TankMovementType(StrEnum):
    delivery = "delivery"
    vehicle_withdrawal = "vehicle_withdrawal"
    external_withdrawal = "external_withdrawal"
    adjustment = "adjustment"


class SubscriptionTier(StrEnum):
    free = "free"
    pro = "pro"
    farm = "farm"
    partner = "partner"


class SubscriptionStatus(StrEnum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    incomplete = "incomplete"
    unpaid = "unpaid"
    incomplete_expired = "incomplete_expired"
