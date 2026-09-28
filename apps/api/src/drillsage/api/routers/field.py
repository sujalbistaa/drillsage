"""Field overview and the event explorer, served from the field snapshot."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from drillsage.core.errors import Problem
from drillsage.field.schemas import EventOut, EventPage, FieldOverview
from drillsage.field.store import MAX_PAGE, EventQuery, EventSort, SnapshotStore

router = APIRouter(prefix="/api/v1", tags=["field"])

_UNAVAILABLE: dict[int | str, dict[str, Any]] = {
    503: {"model": Problem, "description": "The field snapshot is not built"}
}


def _store(request: Request) -> SnapshotStore:
    store: SnapshotStore = request.app.state.snapshots
    return store


@router.get(
    "/field",
    response_model=FieldOverview,
    responses=_UNAVAILABLE,
    summary="Field overview: wellbores, trajectories, formation tops and event locations",
)
def field_overview(request: Request) -> FieldOverview:
    return _store(request).overview()


@router.get(
    "/events",
    response_model=EventPage,
    responses=_UNAVAILABLE,
    summary="Search drilling events with their evidence",
)
def list_events(
    request: Request,
    *,
    hazard: str | None = None,
    wellbore: str | None = None,
    geological: bool | None = None,
    severity_min: Annotated[int | None, Query(ge=1, le=4)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: EventSort = EventSort.RECENT,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
) -> EventPage:
    query = EventQuery(
        hazard=hazard,
        wellbore=wellbore,
        geological=geological,
        severity_min=severity_min,
        q=q.strip() or None if q else None,
        sort=sort,
        offset=offset,
        limit=limit,
    )
    return _store(request).events(query)


@router.get(
    "/events/{event_id}",
    response_model=EventOut,
    responses={404: {"model": Problem}, 503: _UNAVAILABLE[503]},
    summary="One event with every evidence line",
)
def get_event(request: Request, event_id: int) -> EventOut:
    return _store(request).event(event_id)
