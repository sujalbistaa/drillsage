import math
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from drillsage.domain.trajectory import (
    SurveyStation,
    Trajectory,
    TrajectoryError,
    TvdSource,
    clean_stations,
    compose_with_parent,
    dogleg_rad,
    minimum_curvature,
    reconcile_reported_tvd,
)


def s(md: float, incl: float = 0.0, azi: float = 0.0, **kw: object) -> SurveyStation:
    return SurveyStation(md_m=md, incl_deg=incl, azi_deg=azi, **kw)  # type: ignore[arg-type]


def at(day: int) -> datetime:
    return datetime(2020, 1, day, tzinfo=UTC)


# ------------------------------------------------------------------ minimum curvature


def test_vertical_well_tvd_equals_md() -> None:
    stations = minimum_curvature([s(100), s(500), s(1000)])
    assert [p.tvd_m for p in stations] == pytest.approx([0, 100, 500, 1000])
    assert all(p.north_m == 0 and p.east_m == 0 for p in stations)


def test_straight_slant_hole() -> None:
    incl = 30.0
    stations = minimum_curvature([s(0, incl, 90), s(1000, incl, 90)])
    end = stations[-1]
    assert end.tvd_m == pytest.approx(1000 * math.cos(math.radians(incl)))
    assert end.east_m == pytest.approx(1000 * math.sin(math.radians(incl)))
    assert end.north_m == pytest.approx(0, abs=1e-9)
    assert end.dls_deg_per_30m == pytest.approx(0)


def test_quarter_circle_build_matches_analytic_arc() -> None:
    # Building from vertical to horizontal along a circular arc of radius R: MD = πR/2,
    # and minimum curvature is exact for circular arcs.
    radius = 1000.0
    md = math.pi * radius / 2
    end = minimum_curvature([s(0, 0, 0), s(md, 90, 0)])[-1]
    assert end.tvd_m == pytest.approx(radius)
    assert end.north_m == pytest.approx(radius)
    assert end.dls_deg_per_30m == pytest.approx(90 / md * 30)


def test_dogleg_of_azimuth_turn_in_horizontal_hole() -> None:
    assert math.degrees(dogleg_rad(90, 0, 90, 45)) == pytest.approx(45)


def test_minimum_curvature_rejects_bad_input() -> None:
    with pytest.raises(TrajectoryError):
        minimum_curvature([])
    with pytest.raises(TrajectoryError):
        minimum_curvature([s(100), s(100)])


stations_strategy = st.lists(
    st.tuples(
        st.floats(min_value=1, max_value=200),
        st.floats(min_value=0, max_value=120),
        st.floats(min_value=0, max_value=360, exclude_max=True),
    ),
    min_size=1,
    max_size=30,
)


@given(stations_strategy)
@settings(max_examples=200)
def test_geometry_properties(steps: list[tuple[float, float, float]]) -> None:
    md = 0.0
    raw = []
    for step, incl, azi in steps:
        md += step
        raw.append(s(md, incl, azi))
    path = minimum_curvature(raw)
    for a, b in pairwise(path):
        course = b.md_m - a.md_m
        assert abs(b.tvd_m - a.tvd_m) <= course + 1e-6
        horizontal = math.hypot(b.north_m - a.north_m, b.east_m - a.east_m)
        assert horizontal <= course + 1e-6
        assert b.dls_deg_per_30m >= 0


# ------------------------------------------------------------------ cleaning


def test_clean_drops_invalid_and_keeps_newest_duplicate() -> None:
    cleaned = clean_stations(
        [
            s(200, 1, 10, measured_at=at(1)),
            s(200, 1, 20, measured_at=at(2)),
            s(-5),
            s(300, float("nan")),
            s(100),
        ]
    )
    assert [c.md_m for c in cleaned] == [100, 200]
    assert cleaned[1].azi_deg == 20


def test_later_survey_run_supersedes_pilot_hole() -> None:
    pilot = [s(md, 0.5, 100, measured_at=at(1)) for md in (400, 440, 480, 520, 560)]
    main = [s(md, 8.0, 30, measured_at=at(9)) for md in (420, 470, 540)]
    cleaned = clean_stations([*pilot, *main])
    assert [c.md_m for c in cleaned] == [400, 420, 470, 540, 560]
    assert all(c.incl_deg == 8.0 for c in cleaned if 420 <= c.md_m <= 540)


def test_compose_with_parent_ties_in_at_kickoff() -> None:
    parent = [s(md, 10, 0) for md in (500, 1000, 1500, 2000)]
    own = [s(1300, 20, 90), s(1600, 30, 90)]
    combined, cut = compose_with_parent(own, parent, kickoff_md_m=1200)
    assert cut == 1200
    assert [c.md_m for c in combined] == [500, 1000, 1300, 1600]


def test_compose_with_parent_uses_first_survey_when_shallower_than_kickoff() -> None:
    combined, cut = compose_with_parent([s(900, 5, 0)], [s(500), s(1000)], kickoff_md_m=1200)
    assert cut == 900
    assert [c.md_m for c in combined] == [500, 900]


# ------------------------------------------------------------------ reconciliation


def _slant(n: int, reported: Mapping[int, float | None] | None = None) -> list[SurveyStation]:
    """Straight 30° hole, surveyed every 30 m, reported TVDs correct unless overridden."""
    cos30 = math.cos(math.radians(30))
    out = []
    for i in range(1, n + 1):
        md = 30.0 * i
        tvd: float | None = md * cos30
        if reported and i in reported:
            tvd = reported[i]
        out.append(s(md, 30, 45, tvd_reported_m=tvd))
    return out


def test_isolated_typo_rejected() -> None:
    path = reconcile_reported_tvd(minimum_curvature(_slant(20, {10: 24.8})))
    typo = next(p for p in path if p.md_m == 300)
    assert typo.reported_rejected
    assert typo.tvd_source is TvdSource.ADJUSTED
    assert typo.tvd_m == pytest.approx(300 * math.cos(math.radians(30)))


def test_run_of_typos_rejected() -> None:
    bad = {i: 172.1 - 15 * (i - 8) for i in range(8, 12)}
    path = reconcile_reported_tvd(minimum_curvature(_slant(25, bad)))
    rejected = sorted(p.md_m for p in path if p.reported_rejected)
    assert rejected == [240, 270, 300, 330]


def test_wrong_inclination_run_follows_reported_tvd() -> None:
    # Surveys say 40° between 300 and 600 m but the operator's TVDs follow a 30° hole.
    raw = _slant(30)
    wrong = [replace(st_, incl_deg=40.0) if 300 <= st_.md_m <= 600 else st_ for st_ in raw]
    path = reconcile_reported_tvd(minimum_curvature(wrong))
    assert not any(p.reported_rejected for p in path)
    end = path[-1]
    assert end.tvd_m == pytest.approx(900 * math.cos(math.radians(30)))
    assert end.tvd_mincurv_m < end.tvd_m - 20


def test_no_reported_tvd_keeps_minimum_curvature() -> None:
    raw = [replace(x, tvd_reported_m=None) for x in _slant(5)]
    path = reconcile_reported_tvd(minimum_curvature(raw))
    assert {p.tvd_source for p in path} == {TvdSource.MINIMUM_CURVATURE}


def test_impossible_reported_tvd_is_rejected() -> None:
    path = reconcile_reported_tvd(minimum_curvature(_slant(5, {3: 5000.0})))
    assert next(p for p in path if p.md_m == 90).reported_rejected


def test_short_bad_run_at_the_end_is_rejected_when_grossly_off() -> None:
    path = reconcile_reported_tvd(minimum_curvature(_slant(20, {19: 5.0, 20: 6.0})))
    assert sorted(p.md_m for p in path if p.reported_rejected) == [570, 600]


def test_level_shift_that_never_returns_is_kept() -> None:
    shifted = {i: 30.0 * i * math.cos(math.radians(30)) + 8.0 for i in range(10, 21)}
    path = reconcile_reported_tvd(minimum_curvature(_slant(20, shifted)))
    assert not any(p.reported_rejected for p in path)


# ------------------------------------------------------------------ interpolation


def test_trajectory_interpolation_and_inverse() -> None:
    path = reconcile_reported_tvd(minimum_curvature(_slant(20)))
    trajectory = Trajectory(path)
    cos30 = math.cos(math.radians(30))
    assert trajectory.tvd_at_md(300) == pytest.approx(300 * cos30)
    assert trajectory.tvd_at_md(315) == pytest.approx(315 * cos30)
    assert trajectory.tvd_at_md(700) == pytest.approx(700 * cos30)  # extrapolated
    assert trajectory.tvd_at_md(-10) == pytest.approx(-10)
    md = trajectory.md_at_tvd(400)
    assert md is not None
    assert trajectory.tvd_at_md(md) == pytest.approx(400, abs=1e-6)
    assert trajectory.md_at_tvd(10_000) is None
    assert trajectory.md_at_tvd(-1) == 0.0
    assert trajectory.max_md_m == 600
    assert len(trajectory.stations) == 21
    with pytest.raises(TrajectoryError):
        Trajectory([])


@given(st.floats(min_value=0, max_value=600))
def test_tvd_is_monotonic_in_a_downward_hole(md: float) -> None:
    trajectory = Trajectory(minimum_curvature(_slant(20)))
    assert trajectory.tvd_at_md(md) <= trajectory.tvd_at_md(md + 1.0)
