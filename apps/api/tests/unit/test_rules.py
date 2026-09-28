"""Rule lexicon: each case is modelled on a real Volve sentence (true hit or false alarm)."""

import pytest

from drillsage.domain.hazards import HazardType as H
from drillsage.domain.hazards import is_geological, severity
from drillsage.extract.rules import (
    HitSource,
    Span,
    classify_activity,
    code_hits,
    depths_in,
    mitigation_hits,
    outcome_hits,
    sentence_bounds,
    text_hits,
)


def hazards(text: str) -> set[H]:
    return {h.hazard for h in text_hits(text)}


@pytest.mark.parametrize(
    ("text", "hazard"),
    [
        ("BEGAN LOSING MUD AT 15 M3/HR. REDUCED CIRCULATING RATE.", H.LOST_CIRCULATION),
        ("Average losses 1.5 m3/hr while drilling.", H.LOST_CIRCULATION),
        ("HOLE PACKED OFF.  LOST RETURNS. UNABLE TO ROTATE.", H.LOST_CIRCULATION),
        ("OBSERVED WELL FLOWING, GAINED 1,1 M3.", H.WELL_CONTROL),
        ("INITIAL SICP/SIDPP 17 BAR/17 BAR.", H.WELL_CONTROL),
        ("CIRCULATED DUE TO HIGH GAS LEVEL - MAXIMUM READING OF 18%.", H.WELL_CONTROL),
        ("PIPE STUCK AT 1493M WITHOUT ANY WARNING SIGNS.", H.STUCK_PIPE),
        ("JARRED DOWN WITH NO PROGRESS.", H.STUCK_PIPE),
        ("WORKED PIPE FREE WITH 40 TONS OVERPULL.", H.STUCK_PIPE),
        ("Observed tight spots at 284m MD and 272m MD with maximum 20MT overpull", H.TIGHT_HOLE),
        ("POOH with 17 1/2 BHA. Took 29 MT overpull at 315 m.", H.TIGHT_HOLE),
        ("CONT. RIH TO 3884M, TOOK WEIGHT.", H.TIGHT_HOLE),
        ("BACK-REAMED TO 1483M.", H.TIGHT_HOLE),
        ("HAD INCREASING AMOUNT OF CAVINGS IN RETURNS.", H.WELLBORE_INSTABILITY),
        ("Hole packed off and pump pressure increased from 38 to 68 bars.", H.WELLBORE_INSTABILITY),
        ("H2S IN PIPE FROM 9 PPM TO 17 PPM.", H.SHALLOW_GAS_H2S),
        ("PLACED CEMENT. PLUG DID NOT BUMP.", H.CEMENTING),
        ("Performed remedial cement job.", H.CEMENTING),
        ("Unable to build required angle.", H.DIRECTIONAL),
        ("INVESTIGATED FAILURE ON DRAW WORK SPEED CONTROL SYSTEM.", H.EQUIPMENT_FAILURE),
        ("FOUND WASH OUT IN DRILLING PUP JT SHOULDER.", H.EQUIPMENT_FAILURE),
        ("RIH AND ENGAGED FISH AT 3675M.", H.FISHING_JUNK),
        ("FOUND HWDP JOINT SEVERED; LEFT IN HOLE BIT AND STAB.", H.FISHING_JUNK),
        ("WOW to skid rig to F-7. Wind 41-53 kt.", H.WAITING),
    ],
)
def test_true_hits(text: str, hazard: H) -> None:
    assert hazard in hazards(text)


@pytest.mark.parametrize(
    ("text", "hazard"),
    [
        ("Performed kick drill 45sec. Flow checked well, well static.", H.WELL_CONTROL),
        ("Initiated kick off according to DDs instructions.", H.WELL_CONTROL),
        ("Opened kick valve and observed no flow.", H.WELL_CONTROL),
        ("Made up kick joint with FOSV and tested same - ok.", H.WELL_CONTROL),
        ("NO GAINS, NO LOSSES OF MUD FOR THE DAY.", H.LOST_CIRCULATION),
        ("CIRCULATION RATE 1500 LPM. NO LOSSES.", H.LOST_CIRCULATION),
        ("LOST 3,5 M3 MUD FROM LEAK IN SLIP JOINT.", H.LOST_CIRCULATION),
        ("Pressured up; No returns on A-annulus.", H.LOST_CIRCULATION),
        ("LANDED BOP.  OVERPULL TESTED WITH 25 TONS.", H.TIGHT_HOLE),
        ("PU 7 MT overpull on riser/multibowl to ensure slips was set.", H.TIGHT_HOLE),
        ("Set down weight to 55 MT on the TBC and PBR.", H.TIGHT_HOLE),
        ("Pulled back into shoe to confirm no restrictions observed.", H.TIGHT_HOLE),
        ("POOH AND LAID DOWN PACKOFF RUNNING TOOL.", H.WELLBORE_INSTABILITY),
        ("Picked off bottom due to wash out in mud pump 1 piston.", H.WELLBORE_INSTABILITY),
        ("Laid out singles due to stuck protectors.", H.STUCK_PIPE),
        ("Casing tong stuck on casing coupling.", H.STUCK_PIPE),
        ("Focused on potential for stuck pipe.", H.STUCK_PIPE),
        ("drill collar stand went stuck in the fingerboard.", H.STUCK_PIPE),
        ("Treated pits with H2S scavanger.", H.SHALLOW_GAS_H2S),
        ("CHECKED COREBARREL FOR H2S GAS, NO GAS PRESENT.", H.SHALLOW_GAS_H2S),
        ("Drilled soft cement in shoe track from 3414 m to 3434 m.", H.CEMENTING),
        ("Reset and tested anti collision system.", H.DIRECTIONAL),
        ("Installed and made up overshot joint to BOP.", H.FISHING_JUNK),
        ("Observed dropped object on drillfloor.", H.FISHING_JUNK),
        ("Attempted to pressure test; failed due to leaking dart.", H.WELLBORE_INSTABILITY),
    ],
)
def test_routine_wording_is_not_a_hazard(text: str, hazard: H) -> None:
    assert hazard not in hazards(text)


def test_spans_resolve_to_the_trigger_text() -> None:
    text = "Drilled ahead. At 3010 m observed losses of 20 m3/h; pumped LCM pill, losses cured."
    hits = text_hits(text)
    assert [h.span.of(text) for h in hits if h.span] == ["losses", "losses"]
    assert [h.depths_m for h in hits] == [(3010.0,), ()]  # "losses cured" states no depth


def test_depths_ignore_volumes_tonnes_and_tvd() -> None:
    text = "Took 20 MT at 3087M, pumped 10 m3, 2650 m TVD, 2707 m MD, 1.55 SG, 3 1/2 in, 500 lpm"
    assert depths_in(text, Span(0, len(text))) == (3087.0, 2707.0)
    assert depths_in("at 3545,5M", Span(0, 10)) == (3545.5,)


def test_sentence_bounds_do_not_split_decimals() -> None:
    text = "Mud 1.55 SG in hole. Losses at 3000 m; cured"
    bounds = sentence_bounds(text, text.index("Losses"))
    assert bounds.of(text) == " Losses at 3000 m"
    first = sentence_bounds(text, 2)
    assert first.of(text) == "Mud 1.55 SG in hole"


def test_code_rules() -> None:
    assert {
        h.hazard for h in code_hits("interruption -- lost circulation", "circulation loss")
    } == {H.LOST_CIRCULATION}
    assert len(code_hits("interruption -- lost circulation", "circulation loss")) == 2
    assert {h.hazard for h in code_hits("drilling -- trip", "stuck equipment")} == {H.STUCK_PIPE}
    assert code_hits("drilling -- drill", "success") == []
    hits = classify_activity("interruption -- fish", "success", "RIH AND ENGAGED FISH AT 3675M.")
    assert [h.source for h in hits] == [HitSource.CODE, HitSource.TEXT]
    assert classify_activity(None, None, None) == []


def test_mitigations_and_outcomes() -> None:
    text = "Pumped 10 m3 LCM pill; losses cured. Jarred up, no success."
    actions = {m.action for m in mitigation_hits(text)}
    assert {"Pumped LCM pill", "Jarred"} <= actions
    outcomes = [(o.success, o.span.of(text)) for o in outcome_hits(text)]
    assert (True, "losses cured") in outcomes
    assert (False, "no success") in outcomes
    assert list(mitigation_hits(None)) == []
    assert list(outcome_hits("")) == []
    assert not {m.action for m in mitigation_hits("Did not jar the string.")} & {"Jarred"}


def test_severity_bands_and_escalation() -> None:
    assert [severity(h) for h in (0.5, 1, 5.9, 6, 23, 24, 100)] == [1, 2, 2, 3, 3, 4, 4]
    assert severity(0.5, led_to_sidetrack=True) == 2
    assert severity(30, led_to_sidetrack=True) == 4
    assert is_geological(H.LOST_CIRCULATION)
    assert not is_geological(H.WAITING)
