from enum import Enum


class VehicleType(str, Enum):
    car = "car"
    motorcycle = "motorcycle"
    tractor = "tractor"
    machine = "machine"


class FuelType(str, Enum):
    diesel = "diesel"
    petrol = "petrol"


class Role(str, Enum):
    admin = "admin"
    contributor = "contributor"
    reader = "reader"


class UsageUnit(str, Enum):
    km = "km"
    hours = "hours"


VTYPE_TO_USAGE_UNIT: dict[VehicleType, UsageUnit] = {
    VehicleType.car: UsageUnit.km,
    VehicleType.motorcycle: UsageUnit.km,
    VehicleType.tractor: UsageUnit.hours,
    VehicleType.machine: UsageUnit.hours,
}
