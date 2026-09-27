"""Canonical units and conversion from source units of measure (`uom` attributes).

DrillSage stores every quantity in one canonical unit per quantity kind and converts only at
the edges (ingest in, UI out). Field names carry the canonical unit (`md_m`, `density_gcc`).

Canonical units:

| Kind               | Canonical | Field suffix |
|--------------------|-----------|--------------|
| length / depth     | m         | `_m`         |
| density            | g/cm3     | `_gcc`       |
| duration           | h         | `_h`         |
| rate of penetration| m/h       | `_mph`       |
| angle              | deg       | `_deg`       |
| pressure           | kPa       | `_kpa`       |
| temperature        | degC      | `_degc`      |
| dynamic viscosity  | mPa.s     | `_mpas`      |
| yield stress       | Pa        | `_pa`        |
| funnel viscosity   | s (Marsh) | `_s`         |
| concentration      | ppm       | `_ppm`       |
| fraction           | %         | `_pct`       |
| linear mass        | kg/m      | `_kgpm`      |
| volume             | m3        | `_m3`        |
| volume rate        | m3/d      | `_m3pd`      |
| volume ratio       | m3/m3     | `_m3pm3`     |

WITSML writes missing values as the sentinel `-999.99` (sometimes `-999.25`); those become None.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from drillsage.core.errors import InvalidInputError

NULL_SENTINELS: Final = frozenset({-999.99, -999.25, -9999.0})

PPG_PER_GCC: Final = 8.345404452
"""US pounds per gallon in one g/cm3 (the UI toggle uses this)."""

FT_PER_M: Final = 1.0 / 0.3048


class Kind(StrEnum):
    LENGTH = "length"
    DENSITY = "density"
    DURATION = "duration"
    ROP = "rop"
    ANGLE = "angle"
    PRESSURE = "pressure"
    TEMPERATURE = "temperature"
    VISCOSITY = "viscosity"
    YIELD_STRESS = "yield_stress"
    FUNNEL_VISCOSITY = "funnel_viscosity"
    CONCENTRATION = "concentration"
    FRACTION = "fraction"
    LINEAR_MASS = "linear_mass"
    VOLUME = "volume"
    VOLUME_RATE = "volume_rate"
    VOLUME_RATIO = "volume_ratio"


CANONICAL: Final[Mapping[Kind, str]] = {
    Kind.LENGTH: "m",
    Kind.DENSITY: "g/cm3",
    Kind.DURATION: "h",
    Kind.ROP: "m/h",
    Kind.ANGLE: "deg",
    Kind.PRESSURE: "kPa",
    Kind.TEMPERATURE: "degC",
    Kind.VISCOSITY: "mPa.s",
    Kind.YIELD_STRESS: "Pa",
    Kind.FUNNEL_VISCOSITY: "s",
    Kind.CONCENTRATION: "ppm",
    Kind.FRACTION: "%",
    Kind.LINEAR_MASS: "kg/m",
    Kind.VOLUME: "m3",
    Kind.VOLUME_RATE: "m3/d",
    Kind.VOLUME_RATIO: "m3/m3",
}

_FT: Final = 0.3048
_IN: Final = 0.0254
_PSI_KPA: Final = 6.894757293168361

# Multiplicative factors to the canonical unit, per kind. Temperature is affine; see below.
_FACTORS: Final[Mapping[Kind, Mapping[str, float]]] = {
    Kind.LENGTH: {
        "m": 1.0,
        "cm": 0.01,
        "mm": 0.001,
        "km": 1000.0,
        "ft": _FT,
        "in": _IN,
        "in/32": _IN / 32.0,
    },
    Kind.DENSITY: {
        "g/cm3": 1.0,
        "sg": 1.0,
        "kg/m3": 0.001,
        "kg/l": 1.0,
        "ppg": 1.0 / PPG_PER_GCC,
        "lbm/galUS": 1.0 / PPG_PER_GCC,
    },
    Kind.DURATION: {"h": 1.0, "min": 1.0 / 60.0, "s": 1.0 / 3600.0, "d": 24.0},
    Kind.ROP: {"m/h": 1.0, "ft/h": _FT, "m/min": 60.0},
    Kind.ANGLE: {"dega": 1.0, "deg": 1.0, "rad": 57.29577951308232},
    Kind.PRESSURE: {
        "kPa": 1.0,
        "Pa": 0.001,
        "MPa": 1000.0,
        "bar": 100.0,
        "psi": _PSI_KPA,
        # Gauge pressure is kept as gauge; the field name says so where it matters.
        "psig": _PSI_KPA,
    },
    Kind.VISCOSITY: {"mPa.s": 1.0, "cP": 1.0, "Pa.s": 1000.0},
    Kind.YIELD_STRESS: {"Pa": 1.0, "lbf/100ft2": 0.4788025898},
    Kind.FUNNEL_VISCOSITY: {"s": 1.0},
    Kind.CONCENTRATION: {"ppm": 1.0, "mg/l": 1.0, "%": 10_000.0},
    Kind.FRACTION: {"%": 1.0},
    Kind.LINEAR_MASS: {"kg/m": 1.0, "lbm/ft": 1.488163943569554},
    Kind.VOLUME: {"m3": 1.0, "cm3": 1e-6, "l": 0.001, "bbl": 0.158987294928, "M(m3)": 1e6},
    Kind.VOLUME_RATE: {"m3/d": 1.0, "M(m3)/d": 1e6, "bbl/d": 0.158987294928},
    Kind.VOLUME_RATIO: {"m3/m3": 1.0},
}

_TEMPERATURE_UNITS: Final = frozenset({"degC", "degF", "K"})


class UnitError(InvalidInputError):
    """A value arrived in a unit of measure DrillSage does not know how to convert."""

    slug = "unit-error"


def is_null_sentinel(value: float) -> bool:
    return value in NULL_SENTINELS


def supported_units(kind: Kind) -> frozenset[str]:
    if kind is Kind.TEMPERATURE:
        return _TEMPERATURE_UNITS
    return frozenset(_FACTORS[kind])


def to_canonical(value: float, uom: str | None, kind: Kind) -> float:
    """Convert `value` expressed in `uom` to the canonical unit of `kind`.

    A missing `uom` is only accepted when the kind is unambiguous (fractions); guessing units
    for depths or densities is how offset-well comparisons go silently wrong.
    """
    if uom is None:
        if kind is Kind.FRACTION:
            return value
        raise UnitError(f"missing unit of measure for a {kind.value} value")
    if kind is Kind.TEMPERATURE:
        if uom == "degC":
            return value
        if uom == "degF":
            return (value - 32.0) * 5.0 / 9.0
        if uom == "K":
            return value - 273.15
        raise UnitError(f"unknown temperature unit {uom!r}")
    factor = _FACTORS[kind].get(uom)
    if factor is None:
        raise UnitError(f"unknown {kind.value} unit {uom!r}")
    return value * factor


def from_canonical(value: float, uom: str, kind: Kind) -> float:
    """Inverse of `to_canonical` (used at the UI/API edge and in round-trip tests)."""
    if kind is Kind.TEMPERATURE:
        if uom == "degC":
            return value
        if uom == "degF":
            return value * 9.0 / 5.0 + 32.0
        if uom == "K":
            return value + 273.15
        raise UnitError(f"unknown temperature unit {uom!r}")
    factor = _FACTORS[kind].get(uom)
    if factor is None:
        raise UnitError(f"unknown {kind.value} unit {uom!r}")
    return value / factor
