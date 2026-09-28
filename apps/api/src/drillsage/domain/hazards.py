"""Hazard taxonomy (canonical, shared by every extractor and the risk engine).

Geological hazards depend on where the bit is (formation, depth, pressure regime) and drive
look-ahead depth alerts. Operational ones are NPT that the offset-well statistics report but
never place on the depth strip.
"""

from enum import StrEnum
from typing import Final


class HazardType(StrEnum):
    LOST_CIRCULATION = "LOST_CIRCULATION"
    WELL_CONTROL = "WELL_CONTROL"
    """Kick, influx, gain, gas peak."""
    STUCK_PIPE = "STUCK_PIPE"
    TIGHT_HOLE = "TIGHT_HOLE"
    """Overpull, drag, reaming through tight spots, restrictions."""
    WELLBORE_INSTABILITY = "WELLBORE_INSTABILITY"
    """Cavings, pack-off, washout, fill."""
    SHALLOW_GAS_H2S = "SHALLOW_GAS_H2S"
    CEMENTING = "CEMENTING"
    CASING_RUNNING = "CASING_RUNNING"
    DIRECTIONAL = "DIRECTIONAL"
    EQUIPMENT_FAILURE = "EQUIPMENT_FAILURE"
    FISHING_JUNK = "FISHING_JUNK"
    WAITING = "WAITING"
    """Weather and other waiting: NPT, not a geological hazard."""


GEOLOGICAL: Final = frozenset(
    {
        HazardType.LOST_CIRCULATION,
        HazardType.WELL_CONTROL,
        HazardType.STUCK_PIPE,
        HazardType.TIGHT_HOLE,
        HazardType.WELLBORE_INSTABILITY,
        HazardType.SHALLOW_GAS_H2S,
    }
)
"""Hazards that belong to a place in the ground and so drive depth alerts."""


def is_geological(hazard: HazardType) -> bool:
    return hazard in GEOLOGICAL


SEVERITY_NPT_BANDS_H: Final = (1.0, 6.0, 24.0)
"""NPT upper bounds for severities 1, 2 and 3; anything longer is severity 4."""


def severity(npt_h: float, *, led_to_sidetrack: bool = False) -> int:
    """Severity 1 (minor) to 4 (major) from lost time, escalated when the hole was abandoned.

    | Severity | NPT        | Meaning                                  |
    |----------|------------|------------------------------------------|
    | 1        | < 1 h      | noted, handled in stride                 |
    | 2        | 1 to 6 h   | interrupted operations                   |
    | 3        | 6 to 24 h  | lost a day or most of one                |
    | 4        | >= 24 h    | major, or the section had to be redrilled|
    """
    level = 1 + sum(npt_h >= bound for bound in SEVERITY_NPT_BANDS_H)
    if led_to_sidetrack:
        level = min(4, level + 1)
    return level
