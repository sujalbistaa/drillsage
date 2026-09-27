"""Lithostratigraphy: basin packs, formation-name resolution and formation-at-depth lookup.

A *basin pack* is the configurable dictionary of stratigraphic units for one basin (North Sea
for Volve, Assam-Arakan for Oil India). Every formation name that arrives from a report is
resolved against the active pack. Names that do not resolve are kept but flagged, because a
formation from the wrong basin (Volve DDRs contain a few Norwegian Sea tops) must never drive
an offset-well alignment.
"""

import re
import statistics
import unicodedata
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum


class StratLevel(StrEnum):
    GROUP = "group"
    FORMATION = "formation"
    MEMBER = "member"


class TopSource(StrEnum):
    SODIR = "sodir"
    """Regulator-interpreted lithostratigraphy (authoritative, MD from RKB)."""
    DDR = "ddr"
    """Tops picked by the wellsite geologist in the daily report `stratInfo`."""
    CORRELATED = "correlated"
    """No picks in this wellbore: placed at the unit's median TVDSS across the field's wells.
    Lower confidence; shown as such."""


@dataclass(frozen=True, slots=True)
class StratUnit:
    name: str
    level: StratLevel
    group: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BasinPack:
    key: str
    name: str
    units: tuple[StratUnit, ...]
    _index: dict[str, StratUnit] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        index: dict[str, StratUnit] = {}
        for unit in self.units:
            for spelling in (unit.name, *unit.aliases):
                key = name_key(spelling)
                if key in index and index[key] != unit:
                    raise ValueError(f"basin pack {self.key!r}: {spelling!r} is ambiguous")
                index[key] = unit
        object.__setattr__(self, "_index", index)

    def resolve(self, raw_name: str) -> StratUnit | None:
        """The unit a reported name refers to, or None when the pack does not know it."""
        return self._index.get(name_key(raw_name))

    def order(self, unit: StratUnit) -> int:
        """Position of the unit in the pack (packs list units top to bottom)."""
        return self.units.index(unit)


_LEVEL_WORDS = {
    "FM": "FM",
    "FORMATION": "FM",
    "GP": "GP",
    "GROUP": "GP",
    "MBR": "MBR",
    "MEMBER": "MBR",
}
_NON_WORD = re.compile(r"[^\w\s]|_")


def name_key(raw: str) -> str:
    """Spelling-insensitive key: `'Balder Fm .'`, `'BALDER FORMATION'` → `'BALDER FM'`.

    Diacritics are kept distinct from their base letters only through NFC normalisation
    (`Blodøks` stays `BLODØKS`), since stripping them would merge different Norwegian names.
    """
    text = unicodedata.normalize("NFC", raw).upper()
    text = _NON_WORD.sub(" ", text.replace(".", " "))
    words = [_LEVEL_WORDS.get(w, w) for w in text.split()]
    return " ".join(words)


@dataclass(frozen=True, slots=True)
class FormationTop:
    name: str
    """Canonical unit name from the basin pack, or the raw name when unresolved."""
    level: StratLevel
    md_top_m: float
    tvd_top_m: float | None
    source: TopSource
    recognised: bool
    raw_name: str
    inherited_from: str | None = None
    """Parent wellbore the top was inherited from (sidetracks share the hole above kick-off)."""


def resolve_top(
    pack: BasinPack,
    raw_name: str,
    md_top_m: float,
    tvd_top_m: float | None,
    source: TopSource,
) -> FormationTop:
    unit = pack.resolve(raw_name)
    if unit is None:
        guessed = StratLevel.GROUP if name_key(raw_name).endswith(" GP") else StratLevel.FORMATION
        return FormationTop(
            name=raw_name.strip(),
            level=guessed,
            md_top_m=md_top_m,
            tvd_top_m=tvd_top_m,
            source=source,
            recognised=False,
            raw_name=raw_name,
        )
    return FormationTop(
        name=unit.name,
        level=unit.level,
        md_top_m=md_top_m,
        tvd_top_m=tvd_top_m,
        source=source,
        recognised=True,
        raw_name=raw_name,
    )


def consolidate_tops(tops: Iterable[FormationTop]) -> list[FormationTop]:
    """One top per (unit, level), recognised units only, sorted by MD.

    Sodir tops win over DDR picks; among DDR picks of the same unit (a geologist revising a
    pick over several days) the shallowest MD is kept, since the top is where the unit was
    first penetrated.
    """
    best: dict[tuple[str, StratLevel], FormationTop] = {}
    for top in tops:
        if not top.recognised:
            continue
        key = (top.name, top.level)
        current = best.get(key)
        if current is None or _preferred(top, current):
            best[key] = top
    return sorted(best.values(), key=lambda t: (t.md_top_m, t.level != StratLevel.GROUP))


_SOURCE_RANK = {TopSource.SODIR: 0, TopSource.DDR: 1, TopSource.CORRELATED: 2}


def _preferred(candidate: FormationTop, current: FormationTop) -> bool:
    if candidate.source != current.source:
        return _SOURCE_RANK[candidate.source] < _SOURCE_RANK[current.source]
    return candidate.md_top_m < current.md_top_m


def inherit_from_parent(
    own: Sequence[FormationTop],
    parent: Sequence[FormationTop],
    kickoff_md_m: float,
    parent_name: str,
) -> list[FormationTop]:
    """A sidetrack's tops: its own picks plus the parent's tops above the kick-off.

    Geologists often log "formation at kick-off" in a sidetrack's first report; that is not a
    top, and the parent's shallower pick of the same unit wins in `consolidate_tops`.
    """
    inherited = [
        replace(t, inherited_from=t.inherited_from or parent_name)
        for t in parent
        if t.md_top_m < kickoff_md_m
    ]
    return consolidate_tops([*own, *inherited])


MIN_CORRELATION_SUPPORT = 3


def field_median_tvdss(
    tops_tvdss: Iterable[tuple[FormationTop, float]],
) -> dict[tuple[str, StratLevel], float]:
    """Median TVDSS of each unit's top over wellbores that picked it (inherited tops excluded).

    Units picked in fewer than `MIN_CORRELATION_SUPPORT` wellbores are left out.
    """
    samples: dict[tuple[str, StratLevel], list[float]] = {}
    for top, tvdss in tops_tvdss:
        if top.inherited_from is None and top.source is not TopSource.CORRELATED:
            samples.setdefault((top.name, top.level), []).append(tvdss)
    return {
        key: statistics.median(values)
        for key, values in samples.items()
        if len(values) >= MIN_CORRELATION_SUPPORT
    }


def correlate_tops(
    field_tvdss: Mapping[tuple[str, StratLevel], float],
    md_at_tvd: Callable[[float], float | None],
    kb_elevation_m: float,
) -> list[FormationTop]:
    """Tops for a wellbore with no picks, placed at the field's median TVDSS of each unit."""
    tops: list[FormationTop] = []
    for (name, level), tvdss in sorted(field_tvdss.items()):
        tvd = tvdss + kb_elevation_m
        md = md_at_tvd(tvd)
        if md is None:
            continue
        tops.append(
            FormationTop(
                name=name,
                level=level,
                md_top_m=md,
                tvd_top_m=tvd,
                source=TopSource.CORRELATED,
                recognised=True,
                raw_name=name,
            )
        )
    return consolidate_tops(tops)


def unit_at_md(
    tops: Sequence[FormationTop], md_m: float, level: StratLevel = StratLevel.FORMATION
) -> FormationTop | None:
    """The unit at `level` whose top is the deepest one at or above `md_m`.

    Tops are compared by MD within one wellbore (they were picked along that hole); crossing
    to other wells happens through the unit name, never through raw depth.
    """
    candidates = sorted((t for t in tops if t.level == level), key=lambda t: t.md_top_m)
    mds = [t.md_top_m for t in candidates]
    i = bisect_right(mds, md_m) - 1
    return candidates[i] if i >= 0 else None
