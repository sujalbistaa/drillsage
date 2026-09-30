"""Serve the field snapshot: load it once, reload when the file changes, answer queries."""

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from drillsage.core.errors import DependencyUnavailableError, NotFoundError
from drillsage.field.schemas import EventOut, EventPage, EventPoint, FieldOverview, FieldSnapshot
from drillsage.field.snapshot import SNAPSHOT_PATH, read_snapshot

MAX_PAGE: Final = 100


class EventSort(StrEnum):
    RECENT = "recent"
    NPT = "npt"
    SEVERITY = "severity"
    DEPTH = "depth"


@dataclass(frozen=True, slots=True)
class EventQuery:
    hazard: str | None = None
    wellbore: str | None = None
    geological: bool | None = None
    severity_min: int | None = None
    q: str | None = None
    sort: EventSort = EventSort.RECENT
    offset: int = 0
    limit: int = 25


def _matches(event: EventOut, query: EventQuery) -> bool:
    if query.hazard is not None and event.hazard != query.hazard:
        return False
    if query.wellbore is not None and event.wellbore != query.wellbore:
        return False
    if query.geological is not None and event.geological != query.geological:
        return False
    if query.severity_min is not None and event.severity < query.severity_min:
        return False
    if query.q:
        needle = query.q.casefold()
        haystack = [
            event.wellbore,
            event.formation or "",
            event.subtype or "",
            *(line.text for line in event.evidence),
            *(m.action for m in event.mitigations),
        ]
        return any(needle in text.casefold() for text in haystack)
    return True


def _sort_key(sort: EventSort) -> Callable[[EventOut], tuple[float, ...]]:
    match sort:
        case EventSort.RECENT:
            return lambda e: (e.start_at.timestamp(), e.id)
        case EventSort.NPT:
            return lambda e: (e.npt_h, e.id)
        case EventSort.SEVERITY:
            return lambda e: (e.severity, e.npt_h, e.id)
        case EventSort.DEPTH:
            return lambda e: (e.tvdss_top_m if e.tvdss_top_m is not None else -1.0, e.id)


def query_events(events: Sequence[EventOut], query: EventQuery) -> EventPage:
    """Filter, sort (descending, except depth which runs shallow to deep) and page."""
    matching = [e for e in events if _matches(e, query)]
    key = _sort_key(query.sort)
    matching.sort(key=key, reverse=query.sort != EventSort.DEPTH)
    limit = max(1, min(query.limit, MAX_PAGE))
    offset = max(0, query.offset)
    return EventPage(
        total=len(matching),
        offset=offset,
        limit=limit,
        npt_h=round(sum(e.npt_h for e in matching), 1),
        items=matching[offset : offset + limit],
    )


def overview(snapshot: FieldSnapshot) -> FieldOverview:
    return FieldOverview(
        version=snapshot.version,
        generated_at=snapshot.generated_at,
        field=snapshot.field,
        basin_pack=snapshot.basin_pack,
        extractor_version=snapshot.extractor_version,
        attribution=snapshot.attribution,
        stats=snapshot.stats,
        hazards=snapshot.hazards,
        formations=snapshot.formations,
        wellbores=snapshot.wellbores,
        events=[
            EventPoint(
                id=e.id,
                wellbore=e.wellbore,
                hazard=e.hazard,
                geological=e.geological,
                start_at=e.start_at,
                md_top_m=e.md_top_m,
                tvdss_top_m=e.tvdss_top_m,
                easting_m=e.easting_m,
                northing_m=e.northing_m,
                formation=e.formation,
                severity=e.severity,
                npt_h=e.npt_h,
            )
            for e in snapshot.events
        ],
    )


@dataclass(frozen=True, slots=True)
class _Loaded:
    mtime_ns: int
    snapshot: FieldSnapshot
    overview: FieldOverview
    by_id: dict[int, EventOut]


class SnapshotStore:
    """Thread-safe, lazily loaded view of `data/processed/web/field-snapshot.json`."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / SNAPSHOT_PATH
        self._data_dir = data_dir
        self._loaded: _Loaded | None = None
        self._lock = threading.Lock()

    def _current(self) -> _Loaded:
        try:
            mtime = self._path.stat().st_mtime_ns
        except FileNotFoundError:
            raise DependencyUnavailableError(
                "The field snapshot has not been built. Run `make snapshot`."
            ) from None
        with self._lock:
            if self._loaded is None or self._loaded.mtime_ns != mtime:
                snapshot = read_snapshot(self._data_dir)
                self._loaded = _Loaded(
                    mtime_ns=mtime,
                    snapshot=snapshot,
                    overview=overview(snapshot),
                    by_id={e.id: e for e in snapshot.events},
                )
            return self._loaded

    def available(self) -> bool:
        """True when the snapshot file exists and matches the schema."""
        try:
            self._current()
        except (DependencyUnavailableError, ValueError):
            return False
        return True

    def overview(self) -> FieldOverview:
        return self._current().overview

    def events(self, query: EventQuery) -> EventPage:
        return query_events(self._current().snapshot.events, query)

    def event(self, event_id: int) -> EventOut:
        event = self._current().by_id.get(event_id)
        if event is None:
            raise NotFoundError(f"No event {event_id} in the field snapshot.")
        return event
