import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from drillsage.core.units import (
    PPG_PER_GCC,
    Kind,
    UnitError,
    from_canonical,
    is_null_sentinel,
    supported_units,
    to_canonical,
)


@pytest.mark.parametrize(
    ("value", "uom", "kind", "expected"),
    [
        (1000.0, "ft", Kind.LENGTH, 304.8),
        (12.25, "in", Kind.LENGTH, 0.31115),
        (16.0, "in/32", Kind.LENGTH, 0.0127),
        (8.345404452, "ppg", Kind.DENSITY, 1.0),
        (1350.0, "kg/m3", Kind.DENSITY, 1.35),
        (90.0, "min", Kind.DURATION, 1.5),
        (100.0, "ft/h", Kind.ROP, 30.48),
        (1.0, "bar", Kind.PRESSURE, 100.0),
        (1.0, "psi", Kind.PRESSURE, 6.894757293168361),
        (212.0, "degF", Kind.TEMPERATURE, 100.0),
        (373.15, "K", Kind.TEMPERATURE, 100.0),
        (28.0, "cP", Kind.VISCOSITY, 28.0),
        (72.0, "lbm/ft", Kind.LINEAR_MASS, 107.14780393700789),
        (0.1, "M(m3)/d", Kind.VOLUME_RATE, 100_000.0),
    ],
)
def test_to_canonical_known_values(value: float, uom: str, kind: Kind, expected: float) -> None:
    assert to_canonical(value, uom, kind) == pytest.approx(expected, rel=1e-9)


def test_unknown_unit_is_an_error_not_a_guess() -> None:
    with pytest.raises(UnitError, match="unknown length unit 'furlong'"):
        to_canonical(1.0, "furlong", Kind.LENGTH)
    with pytest.raises(UnitError, match="unknown temperature unit"):
        to_canonical(1.0, "degR", Kind.TEMPERATURE)
    with pytest.raises(UnitError):
        from_canonical(1.0, "degR", Kind.TEMPERATURE)
    with pytest.raises(UnitError):
        from_canonical(1.0, "furlong", Kind.LENGTH)


def test_missing_unit_rejected_except_for_fractions() -> None:
    with pytest.raises(UnitError, match="missing unit"):
        to_canonical(1.0, None, Kind.LENGTH)
    assert to_canonical(95.0, None, Kind.FRACTION) == 95.0


def test_null_sentinels() -> None:
    assert is_null_sentinel(-999.99)
    assert is_null_sentinel(-999.25)
    assert not is_null_sentinel(-999.0)


def test_ppg_toggle_constant() -> None:
    assert to_canonical(PPG_PER_GCC, "ppg", Kind.DENSITY) == pytest.approx(1.0)


_KINDS_AND_UNITS = [(kind, uom) for kind in Kind for uom in sorted(supported_units(kind))]


@given(
    st.sampled_from(_KINDS_AND_UNITS),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_round_trip_through_canonical(kind_uom: tuple[Kind, str], value: float) -> None:
    kind, uom = kind_uom
    back = from_canonical(to_canonical(value, uom, kind), uom, kind)
    assert math.isclose(back, value, rel_tol=1e-9, abs_tol=1e-9)
