"""Wellbore trajectories by the minimum-curvature method.

Everything here is pure: depths in metres along hole (MD) from the rig's kelly bushing (RKB),
angles in degrees, azimuth clockwise from grid north. Offsets are north/east of the surface
location.

Neither survey column can be trusted blindly, so the two are reconciled:

- Reported TVD carries typing errors, alone (15/9-F-4 reports TVD 24.8 m at MD 2620.8 m) or in
  short runs (15/9-19 BT2, MD 2916 to 3000 m). The residual (reported minus computed TVD) then jumps
  by more than the survey geometry allows, away and back to the same level; such short
  segments are rejected.
- Inclination can be wrong over a run of stations (15/9-F-15 A, MD 1827 to 2392 m: 40° reported
  where the operator's own TVDs imply ~25°). The residual then ramps instead of spiking, and
  the operator's TVD, computed from the original survey, is kept.

The final TVD follows accepted reported values exactly; between and beyond them the
minimum-curvature shape is used, shifted by the linearly interpolated residual. Horizontal
offsets always come from minimum curvature.
"""

import math
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from itertools import pairwise

DLS_COURSE_LENGTH_M = 30.0
"""Dog-leg severity is reported per 30 m (the metric convention)."""

_MAX_INCLINATION_DEG = 180.0
_STRAIGHT_RAD = 1e-9
JUMP_BASE_M = 3.0
JUMP_PER_M = 0.25
"""Residual jumps larger than `JUMP_BASE_M + JUMP_PER_M * ΔMD` split the residual series."""
MAX_BAD_RUN = 8
"""Longest run of stations that can be rejected as a typing error."""
EDGE_JUMP_M = 100.0
"""A short segment at either end is rejected only when it is off by more than this."""


class TrajectoryError(ValueError):
    """The survey data cannot produce a trajectory (for example, no valid stations)."""


@dataclass(frozen=True, slots=True)
class SurveyStation:
    md_m: float
    incl_deg: float
    azi_deg: float
    tvd_reported_m: float | None = None
    measured_at: datetime | None = None


class TvdSource(StrEnum):
    MINIMUM_CURVATURE = "min_curvature"
    """No accepted reported TVD anywhere in the wellbore."""
    REPORTED = "reported"
    """The operator's reported TVD, accepted."""
    ADJUSTED = "adjusted"
    """Minimum curvature shifted onto the neighbouring accepted reported TVDs."""


@dataclass(frozen=True, slots=True)
class TrajectoryStation:
    md_m: float
    incl_deg: float
    azi_deg: float
    tvd_m: float
    """Best TVD estimate (see module docstring)."""
    north_m: float
    east_m: float
    dls_deg_per_30m: float
    tvd_mincurv_m: float
    tvd_reported_m: float | None
    tvd_source: TvdSource
    reported_rejected: bool
    """The reported TVD was identified as a typing error and ignored."""
    inherited: bool
    """True when the station comes from the parent wellbore above the kick-off point."""

    @property
    def tvd_residual_m(self) -> float | None:
        """Reported minus minimum-curvature TVD."""
        if self.tvd_reported_m is None:
            return None
        return self.tvd_reported_m - self.tvd_mincurv_m


def _valid(station: SurveyStation) -> bool:
    return (
        math.isfinite(station.md_m)
        and station.md_m >= 0.0
        and math.isfinite(station.incl_deg)
        and 0.0 <= station.incl_deg <= _MAX_INCLINATION_DEG
        and math.isfinite(station.azi_deg)
    )


def clean_stations(stations: Iterable[SurveyStation]) -> list[SurveyStation]:
    """Drop invalid and superseded stations and de-duplicate by MD, sorted by MD.

    - Daily reports repeat the last stations of the previous day, sometimes with a corrected
      azimuth. For duplicate MDs the most recently measured station wins.
    - A survey run measured on a later day supersedes earlier stations inside its MD span. This
      removes pilot holes (15/9-F-12 drilled a vertical 8 1/2" pilot to 1353 m before the
      deviated 26" hole; both surveys sit in the same reports) and honours re-surveys.
    """
    valid = [s for s in stations if _valid(s)]
    by_day: dict[date | None, list[SurveyStation]] = defaultdict(list)
    for station in valid:
        by_day[station.measured_at.date() if station.measured_at else None].append(station)
    spans = {
        day: (min(s.md_m for s in group), max(s.md_m for s in group))
        for day, group in by_day.items()
        if day is not None and len(group) > 1
    }

    def superseded(station: SurveyStation) -> bool:
        day = station.measured_at.date() if station.measured_at else None
        return any(
            (day is None or later > day) and lo < station.md_m < hi
            for later, (lo, hi) in spans.items()
        )

    by_md: dict[float, SurveyStation] = {}
    for station in valid:
        if superseded(station):
            continue
        key = round(station.md_m, 2)
        current = by_md.get(key)
        if current is None or _newer(station, current):
            by_md[key] = station
    return [by_md[md] for md in sorted(by_md)]


def _newer(candidate: SurveyStation, current: SurveyStation) -> bool:
    if candidate.measured_at is None:
        return False
    if current.measured_at is None:
        return True
    return candidate.measured_at >= current.measured_at


def _ratio_factor(dogleg_rad: float) -> float:
    if dogleg_rad < _STRAIGHT_RAD:
        return 1.0
    return 2.0 / dogleg_rad * math.tan(dogleg_rad / 2.0)


def dogleg_rad(incl1_deg: float, azi1_deg: float, incl2_deg: float, azi2_deg: float) -> float:
    """Angle between two survey tangents (radians)."""
    i1, i2 = math.radians(incl1_deg), math.radians(incl2_deg)
    da = math.radians(azi2_deg - azi1_deg)
    cos_dl = math.cos(i2 - i1) - math.sin(i1) * math.sin(i2) * (1.0 - math.cos(da))
    return math.acos(max(-1.0, min(1.0, cos_dl)))


def minimum_curvature(
    stations: Sequence[SurveyStation], *, inherited_below_md_m: float = -1.0
) -> list[TrajectoryStation]:
    """Integrate clean, MD-sorted stations from a vertical tie-in at MD 0 (RKB).

    Stations with MD < `inherited_below_md_m` are marked as inherited from the parent.
    """
    if not stations:
        raise TrajectoryError("no valid survey stations")
    if any(b.md_m <= a.md_m for a, b in pairwise(stations)):
        raise TrajectoryError("stations must be strictly increasing in MD; run clean_stations")

    tie_in = SurveyStation(md_m=0.0, incl_deg=0.0, azi_deg=0.0)
    path = list(stations) if stations[0].md_m == 0.0 else [tie_in, *stations]

    first = path[0]
    result = [
        TrajectoryStation(
            md_m=first.md_m,
            incl_deg=first.incl_deg,
            azi_deg=first.azi_deg,
            tvd_m=0.0,
            north_m=0.0,
            east_m=0.0,
            dls_deg_per_30m=0.0,
            tvd_mincurv_m=0.0,
            tvd_reported_m=first.tvd_reported_m,
            tvd_source=TvdSource.MINIMUM_CURVATURE,
            reported_rejected=False,
            inherited=first.md_m < inherited_below_md_m,
        )
    ]
    tvd = north = east = 0.0
    for a, b in pairwise(path):
        course = b.md_m - a.md_m
        dl = dogleg_rad(a.incl_deg, a.azi_deg, b.incl_deg, b.azi_deg)
        half_rf = course / 2.0 * _ratio_factor(dl)
        i1, i2 = math.radians(a.incl_deg), math.radians(b.incl_deg)
        a1, a2 = math.radians(a.azi_deg), math.radians(b.azi_deg)
        north += half_rf * (math.sin(i1) * math.cos(a1) + math.sin(i2) * math.cos(a2))
        east += half_rf * (math.sin(i1) * math.sin(a1) + math.sin(i2) * math.sin(a2))
        tvd += half_rf * (math.cos(i1) + math.cos(i2))
        result.append(
            TrajectoryStation(
                md_m=b.md_m,
                incl_deg=b.incl_deg,
                azi_deg=b.azi_deg % 360.0,
                tvd_m=tvd,
                north_m=north,
                east_m=east,
                dls_deg_per_30m=math.degrees(dl) * DLS_COURSE_LENGTH_M / course,
                tvd_mincurv_m=tvd,
                tvd_reported_m=b.tvd_reported_m,
                tvd_source=TvdSource.MINIMUM_CURVATURE,
                reported_rejected=False,
                inherited=b.md_m < inherited_below_md_m,
            )
        )
    return result


def _jump_tolerance_m(delta_md_m: float) -> float:
    return JUMP_BASE_M + JUMP_PER_M * abs(delta_md_m)


def _typo_segments(residual: dict[int, float], mds: Sequence[float]) -> set[int]:
    """Stations whose reported TVD is part of a short excursion away from a consistent level.

    Walking down the hole, a jump in residual larger than the geometry allows starts an
    excursion. If a later station within `MAX_BAD_RUN` returns to the level before the jump,
    everything in between is a typing error. A jump that never returns is a genuine level
    shift and is kept. Short runs at either end are rejected only when grossly off.
    """
    order = sorted(residual)
    rejected: set[int] = set()

    def agrees(a: int, b: int) -> bool:
        return abs(residual[a] - residual[b]) <= _jump_tolerance_m(mds[b] - mds[a])

    k = 0
    while k + 1 < len(order):
        anchor, nxt = order[k], order[k + 1]
        if agrees(anchor, nxt):
            k += 1
            continue
        back = next(
            (
                j
                for j in range(k + 2, min(len(order), k + 2 + MAX_BAD_RUN))
                if agrees(anchor, order[j])
            ),
            None,
        )
        if back is not None:
            rejected.update(order[k + 1 : back])
            k = back
            continue
        tail = order[k + 1 :]
        if len(tail) <= MAX_BAD_RUN and abs(residual[nxt] - residual[anchor]) > EDGE_JUMP_M:
            rejected.update(tail)
            break
        k += 1

    head_end = next(
        (k for k in range(min(MAX_BAD_RUN, len(order) - 1)) if not agrees(order[k], order[k + 1])),
        None,
    )
    if head_end is not None:
        head, first_after = order[: head_end + 1], order[head_end + 1]
        if (
            first_after not in rejected
            and len(order) - len(head) > len(head)
            and abs(residual[head[-1]] - residual[first_after]) > EDGE_JUMP_M
        ):
            rejected.update(head)
    return rejected


def reconcile_reported_tvd(stations: Sequence[TrajectoryStation]) -> list[TrajectoryStation]:
    """Blend minimum-curvature stations with the operator's reported TVDs (module docstring)."""
    residual: dict[int, float] = {}
    for i, s in enumerate(stations):
        reported = s.tvd_reported_m
        if reported is not None and -1.0 <= reported <= s.md_m + 1.0:
            residual[i] = reported - s.tvd_mincurv_m
    rejected = _typo_segments(residual, [s.md_m for s in stations])
    rejected.update(
        i for i, s in enumerate(stations) if s.tvd_reported_m is not None and i not in residual
    )
    indices = sorted(residual)
    accepted = [i for i in indices if i not in rejected]

    result: list[TrajectoryStation] = []
    for i, s in enumerate(stations):
        if i in accepted:
            tvd, source = s.tvd_mincurv_m + residual[i], TvdSource.REPORTED
        elif not accepted:
            tvd, source = s.tvd_mincurv_m, TvdSource.MINIMUM_CURVATURE
        else:
            tvd = s.tvd_mincurv_m + _interpolated_offset(stations, accepted, residual, i)
            source = TvdSource.ADJUSTED
        result.append(replace(s, tvd_m=tvd, tvd_source=source, reported_rejected=i in rejected))
    return result


def _interpolated_offset(
    stations: Sequence[TrajectoryStation],
    accepted: Sequence[int],
    residual: dict[int, float],
    i: int,
) -> float:
    pos = bisect_right(accepted, i)
    if pos == 0:
        first = accepted[0]
        # Above the first accepted station: fade the offset in from zero at surface.
        md0 = stations[first].md_m
        return residual[first] * (stations[i].md_m / md0 if md0 > 0 else 1.0)
    if pos == len(accepted):
        return residual[accepted[-1]]
    lo, hi = accepted[pos - 1], accepted[pos]
    return _lerp(residual[lo], residual[hi], stations[lo].md_m, stations[hi].md_m, stations[i].md_m)


def compose_with_parent(
    own: Sequence[SurveyStation],
    parent: Sequence[SurveyStation],
    kickoff_md_m: float,
) -> tuple[list[SurveyStation], float]:
    """Stations for a sidetrack: the parent's stations above the kick-off plus its own.

    Returns the combined stations and the MD below which stations are inherited. When the
    sidetrack's own first survey is shallower than the stated kick-off, the survey wins: the
    sidetrack cannot have left the parent hole deeper than its first own station.
    """
    own_clean = clean_stations(own)
    cut_md = min(kickoff_md_m, own_clean[0].md_m) if own_clean else kickoff_md_m
    upper = [s for s in clean_stations(parent) if s.md_m < cut_md]
    return clean_stations([*upper, *own_clean]), cut_md


class Trajectory:
    """Interpolates along a computed trajectory (MD→TVD and TVD→MD)."""

    def __init__(self, stations: Sequence[TrajectoryStation]) -> None:
        if not stations:
            raise TrajectoryError("empty trajectory")
        self._stations = list(stations)
        self._mds = [s.md_m for s in self._stations]

    @property
    def stations(self) -> list[TrajectoryStation]:
        return list(self._stations)

    @property
    def max_md_m(self) -> float:
        return self._mds[-1]

    def tvd_at_md(self, md_m: float) -> float:
        """TVD at an arbitrary MD, by minimum-curvature interpolation between stations.

        Below the deepest station the last tangent is extrapolated as a straight line, which
        is the standard assumption for the few metres drilled after the last survey.
        """
        if md_m <= self._mds[0]:
            return self._stations[0].tvd_m - (self._mds[0] - md_m)
        i = bisect_right(self._mds, md_m) - 1
        a = self._stations[i]
        if md_m == a.md_m:
            return a.tvd_m
        if i == len(self._stations) - 1:
            return a.tvd_m + (md_m - a.md_m) * math.cos(math.radians(a.incl_deg))
        b = self._stations[i + 1]
        offset = _lerp(a.tvd_m - a.tvd_mincurv_m, b.tvd_m - b.tvd_mincurv_m, a.md_m, b.md_m, md_m)
        partial = minimum_curvature(
            [
                SurveyStation(md_m=0.0, incl_deg=a.incl_deg, azi_deg=a.azi_deg),
                SurveyStation(
                    md_m=md_m - a.md_m,
                    incl_deg=_lerp(a.incl_deg, b.incl_deg, a.md_m, b.md_m, md_m),
                    azi_deg=_lerp_azimuth(a.azi_deg, b.azi_deg, a.md_m, b.md_m, md_m),
                ),
            ]
        )
        return a.tvd_mincurv_m + partial[-1].tvd_m + offset

    def md_at_tvd(self, tvd_m: float) -> float | None:
        """First MD at which the hole reaches `tvd_m`; None when it never gets that deep."""
        prev = self._stations[0]
        if tvd_m <= prev.tvd_m:
            return prev.md_m
        for station in self._stations[1:]:
            if station.tvd_m >= tvd_m:
                lo, hi = prev.md_m, station.md_m
                for _ in range(50):
                    mid = (lo + hi) / 2.0
                    if self.tvd_at_md(mid) < tvd_m:
                        lo = mid
                    else:
                        hi = mid
                return (lo + hi) / 2.0
            prev = station
        return None


def _lerp(v1: float, v2: float, x1: float, x2: float, x: float) -> float:
    return v1 + (v2 - v1) * (x - x1) / (x2 - x1)


def _lerp_azimuth(a1: float, a2: float, x1: float, x2: float, x: float) -> float:
    delta = (a2 - a1 + 180.0) % 360.0 - 180.0
    return (a1 + delta * (x - x1) / (x2 - x1)) % 360.0
