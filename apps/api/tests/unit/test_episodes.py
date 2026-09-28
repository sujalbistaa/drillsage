from datetime import UTC, datetime, timedelta

from drillsage.domain.hazards import HazardType as H
from drillsage.extract.episodes import (
    ActivityRecord,
    EvidenceKind,
    Outcome,
    extract_events,
    group_into_episodes,
)

T0 = datetime(2020, 1, 1, tzinfo=UTC)
_ids = iter(range(1, 10_000))


def act(
    hour: float,
    hours: float,
    comments: str | None,
    *,
    code: str = "drilling -- drill",
    state: str = "ok",
    detail: str = "success",
    md: float | None = 3000.0,
    report_md: float | None = 3050.0,
    wellbore: str = "W-1",
    report_id: int = 1,
) -> ActivityRecord:
    return ActivityRecord(
        id=next(_ids),
        wellbore=wellbore,
        report_id=report_id,
        seq=0,
        start_at=T0 + timedelta(hours=hour),
        end_at=T0 + timedelta(hours=hour + hours),
        md_m=md,
        report_md_m=report_md,
        proprietary_code=code,
        state=state,
        state_detail=detail,
        comments=comments,
    )


def only(events: list, hazard: H):  # type: ignore[no-untyped-def,type-arg]
    matching = [e for e in events if e.hazard is hazard]
    assert len(matching) == 1, matching
    return matching[0]


def test_consecutive_lines_about_one_problem_form_one_event() -> None:
    records = [
        act(0, 2, "Drilled to 3010 m. Observed losses of 20 m3/h at 3010 m."),
        act(
            2,
            3,
            "Pumped 10 m3 LCM pill.",
            code="interruption -- lost circulation",
            state="fail",
            detail="circulation loss",
        ),
        act(
            5,
            1,
            "Continued circulating; losses cured.",
            code="interruption -- lost circulation",
            state="fail",
            detail="circulation loss",
        ),
        act(20, 1, "Losses again at 3100 m while drilling."),  # 14 h later: a new event
    ]
    drafts = [d for d in group_into_episodes(records) if d.hazard is H.LOST_CIRCULATION]
    assert [len(d.activities) for d in drafts] == [3, 1]

    events = [e for e in extract_events(records, {"W-1": 3200}) if e.hazard is H.LOST_CIRCULATION]
    first = events[0]
    assert (first.md_top_m, first.md_bottom_m, first.depth_source) == (3010, 3010, "text")
    assert first.npt_h == 4.0
    assert first.severity == 2
    assert first.detected_by == "code+text"
    lcm = next(m for m in first.mitigations if m.action == "Pumped LCM pill")
    assert lcm.outcome is Outcome.SUCCESS
    assert lcm.outcome_activity_id == records[2].id
    kinds = {e.kind for e in first.evidence}
    assert kinds == {
        EvidenceKind.CODE,
        EvidenceKind.TRIGGER,
        EvidenceKind.MITIGATION,
        EvidenceKind.OUTCOME,
    }
    for evidence in first.evidence:
        if evidence.span is not None:
            text = next(r.comments for r in records if r.id == evidence.activity_id)
            assert text is not None
            assert evidence.span.of(text)


def test_depth_prefers_the_near_bit_cluster_and_respects_the_mudline() -> None:
    records = [
        act(0, 1, "Hole packed off at 3245 m. POOH from 3245 m to 13 m.", md=13),
    ]
    event = only(extract_events(records, {"W-1": 3300}, {"W-1": 120}), H.WELLBORE_INSTABILITY)
    assert (event.md_top_m, event.md_bottom_m) == (3245, 3245)

    shallow = [act(0, 1, "Worked tight spot.", md=30, report_md=800)]
    tight = only(extract_events(shallow, {"W-1": 900}, {"W-1": 120}), H.TIGHT_HOLE)
    assert (tight.md_top_m, tight.depth_source) == (800, "report")

    surface = [act(0, 1, None, code="interruption -- repair", md=30, report_md=None)]
    repair = only(extract_events(surface, {}, {"W-1": 120}), H.EQUIPMENT_FAILURE)
    assert (repair.md_top_m, repair.depth_source) == (30, "activity")

    nowhere = [act(0, 1, None, code="interruption -- wait", md=None, report_md=None)]
    assert only(extract_events(nowhere, {}), H.WAITING).depth_source == "none"


def test_sidetrack_after_the_problem_escalates_severity() -> None:
    records = [
        act(0, 0.5, "PIPE STUCK AT 2500 M. Jarred up, no success."),
        act(10, 5, "Prepared sidetrack.", code="interruption -- sidetrack"),
    ]
    event = only(extract_events(records, {"W-1": 3000}), H.STUCK_PIPE)
    assert event.led_to_sidetrack
    assert event.severity == 2
    jar = next(m for m in event.mitigations if m.action == "Jarred")
    assert jar.outcome is Outcome.FAILURE


def test_events_are_per_wellbore_and_deterministic() -> None:
    records = [
        act(0, 1, "Took weight at 1500 m.", wellbore="A"),
        act(0, 1, "Took weight at 1500 m.", wellbore="B"),
    ]
    first = extract_events(records, {})
    second = extract_events(list(reversed(records)), {})
    assert [e.wellbore for e in first] == ["A", "B"]
    assert [(e.wellbore, e.md_top_m) for e in first] == [(e.wellbore, e.md_top_m) for e in second]
