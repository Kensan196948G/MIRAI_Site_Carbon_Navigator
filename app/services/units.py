"""Unit conversion engine for common activity units."""

# Conversion factors to a dimension base:
_TO_BASE = {
    # volume -> L
    "mL": 0.001,
    "L": 1.0,
    "kL": 1000.0,
    "m3": 1000.0,
    # mass -> kg
    "g": 0.001,
    "kg": 1.0,
    "t": 1000.0,
    # energy -> kWh
    "Wh": 0.001,
    "kWh": 1.0,
    "MWh": 1000.0,
    # distance -> km
    "m": 0.001,
    "km": 1.0,
    # transport
    "t-km": 1.0,
    "kg-km": 0.001,
    # person-km
    "人-km": 1.0,
    # time
    "h": 1.0,
    "min": 1 / 60,
}

_DIMENSIONS = {
    "mL": "volume", "L": "volume", "kL": "volume", "m3": "volume",
    "g": "mass", "kg": "mass", "t": "mass",
    "Wh": "energy", "kWh": "energy", "MWh": "energy",
    "m": "distance", "km": "distance",
    "t-km": "transport", "kg-km": "transport",
    "人-km": "person_km",
    "h": "time", "min": "time",
}


def list_units() -> list[dict]:
    return [
        {"unit": unit, "dimension": _DIMENSIONS[unit], "base_factor": factor}
        for unit, factor in sorted(_TO_BASE.items())
    ]


def convert(value: float, from_unit: str, to_unit: str) -> dict:
    if from_unit not in _TO_BASE or to_unit not in _TO_BASE:
        raise ValueError(f"Unsupported unit: {from_unit} -> {to_unit}")
    if _DIMENSIONS[from_unit] != _DIMENSIONS[to_unit]:
        raise ValueError(
            f"Dimension mismatch: {from_unit}({_DIMENSIONS[from_unit]}) "
            f"-> {to_unit}({_DIMENSIONS[to_unit]})"
        )
    factor = _TO_BASE[from_unit] / _TO_BASE[to_unit]
    return {
        "value": value,
        "from_unit": from_unit,
        "to_unit": to_unit,
        "converted_value": value * factor,
        "conversion_factor": factor,
    }
