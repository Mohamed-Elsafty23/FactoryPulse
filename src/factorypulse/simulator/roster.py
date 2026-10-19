"""The machine roster. Single source of truth for telemetry and reference data."""

from __future__ import annotations

from dataclasses import dataclass

TYPE_MIX = {"L": 12, "M": 6, "H": 2}

PLANTS = [
    {
        "plant_id": "PL-INGOL",
        "plant_name": "Ingolstadt",
        "country": "DE",
        "timezone": "Europe/Berlin",
    },
    {
        "plant_id": "PL-BRNO",
        "plant_name": "Brno",
        "country": "CZ",
        "timezone": "Europe/Prague",
    },
]

SHIFTS = [
    {
        "shift_sk": 1,
        "shift_name": "early",
        "shift_name_de": "Frühschicht",
        "start_hour": 6,
        "end_hour": 14,
    },
    {
        "shift_sk": 2,
        "shift_name": "late",
        "shift_name_de": "Spätschicht",
        "start_hour": 14,
        "end_hour": 22,
    },
    {
        "shift_sk": 3,
        "shift_name": "night",
        "shift_name_de": "Nachtschicht",
        "start_hour": 22,
        "end_hour": 6,
    },
]

FAILURE_TYPES = [
    {
        "code": "NONE",
        "name_en": "No failure",
        "name_de": "Kein Ausfall",
        "severity": 0,
    },
    {
        "code": "TWF",
        "name_en": "Tool wear failure",
        "name_de": "Werkzeugverschleiß",
        "severity": 2,
    },
    {
        "code": "HDF",
        "name_en": "Heat dissipation failure",
        "name_de": "Wärmeableitungsfehler",
        "severity": 3,
    },
    {
        "code": "PWF",
        "name_en": "Power failure",
        "name_de": "Leistungsausfall",
        "severity": 4,
    },
    {
        "code": "OSF",
        "name_en": "Overstrain failure",
        "name_de": "Überlastungsausfall",
        "severity": 4,
    },
    {
        "code": "RNF",
        "name_en": "Random failure",
        "name_de": "Zufallsausfall",
        "severity": 1,
    },
]

OSF_THRESHOLD = {"L": 11_000, "M": 12_000, "H": 13_000}
WEAR_RATE = {"L": 1.00, "M": 0.80, "H": 0.65}
MODELS = {"L": "HSM-400", "M": "HSM-600", "H": "HSM-900"}


@dataclass(frozen=True)
class Machine:
    """A stable machine in the simulated fleet."""

    machine_id: str
    machine_name: str
    plant_id: str
    line_id: str
    machine_type: str
    model: str
    criticality: str
    ideal_cycle_seconds: float


def build_roster() -> list[Machine]:
    """Deterministically build the 20-machine fleet."""
    machines: list[Machine] = []
    sequence = 0
    for machine_type, count in TYPE_MIX.items():
        for _ in range(count):
            sequence += 1
            plant = PLANTS[(sequence - 1) % len(PLANTS)]["plant_id"]
            line = f"LN-{((sequence - 1) % 4) + 1}"
            criticality = {"H": "high", "M": "medium", "L": "low"}[machine_type]
            machines.append(
                Machine(
                    machine_id=f"MC-{sequence:02d}",
                    machine_name=f"{MODELS[machine_type]} #{sequence:02d}",
                    plant_id=plant,
                    line_id=line,
                    machine_type=machine_type,
                    model=MODELS[machine_type],
                    criticality=criticality,
                    ideal_cycle_seconds=round(28.0 + sequence * 0.37, 2),
                )
            )
    return machines


ROSTER = build_roster()
MACHINE_IDS = [machine.machine_id for machine in ROSTER]
