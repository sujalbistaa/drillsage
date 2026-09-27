"""Wellbore naming.

Norwegian wellbore names follow `<quadrant>/<block>-<well>[ <suffix>]`, for example `15/9-F-1 C`.
DDRs prefix the country (`NO 15/9-F-1 C`); Sodir does not. The canonical form has no prefix
and single spaces.

A trailing `T<n>` (`15/9-19 BT2`, `15/9-F-11 T2`) marks a *technical* sidetrack: the hole was
re-drilled around a problem (stuck pipe, lost BHA) and keeps the regulator's wellbore id.
"""

import re
from dataclasses import dataclass

_COUNTRY_PREFIX = re.compile(r"^(?:NO)\s+")
_WHITESPACE = re.compile(r"\s+")
_TECHNICAL_SIDETRACK = re.compile(r"^(?P<base>.+?)\s*T(?P<n>\d+)$")


def canonical_wellbore_name(raw: str) -> str:
    """`'NO  15/9-F-1   C'` → `'15/9-F-1 C'`."""
    name = _WHITESPACE.sub(" ", raw.strip())
    return _COUNTRY_PREFIX.sub("", name)


@dataclass(frozen=True, slots=True)
class TechnicalSidetrack:
    base: str
    number: int


def technical_sidetrack(name: str) -> TechnicalSidetrack | None:
    """Split `'15/9-19 BT2'` into base `'15/9-19 B'` and number 2; None for other names.

    A suffix letter is required before `T` unless separated by a space (`F-11 T2`), so a
    well literally numbered `...-T2` is not misread.
    """
    match = _TECHNICAL_SIDETRACK.match(canonical_wellbore_name(name))
    if match is None:
        return None
    base = match.group("base").rstrip()
    if base.endswith("-"):
        return None
    return TechnicalSidetrack(base=base, number=int(match.group("n")))
