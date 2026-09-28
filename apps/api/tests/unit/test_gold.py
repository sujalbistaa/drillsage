"""Gold-set sampling, label files and weighted metrics (synthetic lines, no Volve data)."""

import json
from pathlib import Path

import pytest

from drillsage.evaluation import report as gold_report
from drillsage.evaluation.gold import (
    SAMPLE_VERSION,
    UNFLAGGED_STRATUM,
    Label,
    Line,
    activity_key,
    coverage,
    draw_sample,
    micro,
    read_labels,
    rule_predictors,
    score,
    stratum_of,
    write_sample,
)


def line(
    i: int,
    text: str,
    *,
    report: str = "2020-01-01T00:00:00+00:00",
    code: str = "drilling -- drill",
    hazards: tuple[str, ...] = (),
    md: float | None = 2000.0,
) -> Line:
    return Line(
        key=activity_key("W-1", report, i),
        wellbore="W-1",
        report_start=report,
        seq=i,
        start=f"{report[:10]}T0{i % 10}:00:00+00:00",
        end=f"{report[:10]}T0{i % 10}:30:00+00:00",
        md_m=md,
        code=code,
        state="ok",
        state_detail="success",
        text=text,
        rule_hazards=hazards,
    )


LINES = [
    *[line(i, f"Observed losses {i}", hazards=("LOST_CIRCULATION",)) for i in range(30)],
    *[line(100 + i, f"Drilled ahead {i}", report="2020-01-02T00:00:00+00:00") for i in range(500)],
]


def test_sample_is_seeded_stratified_and_weighted() -> None:
    items = draw_sample(LINES, per_hazard=10, unflagged=50)
    assert [i.line.key for i in items] == [
        i.line.key for i in draw_sample(LINES, per_hazard=10, unflagged=50)
    ]
    by = {s: [i for i in items if i.stratum == s] for s in {i.stratum for i in items}}
    assert len(by["LOST_CIRCULATION"]) == 10
    assert len(by[UNFLAGGED_STRATUM]) == 50
    assert {i.weight for i in by["LOST_CIRCULATION"]} == {3.0}
    assert {i.weight for i in by[UNFLAGGED_STRATUM]} == {10.0}
    assert stratum_of(LINES[0]) == "LOST_CIRCULATION"
    # Context lines never cross into another report (day one: losses; day two: drilling).
    for item in items:
        context = " ".join(item.before + item.after)
        if item.stratum == UNFLAGGED_STRATUM:
            assert "losses" not in context
        else:
            assert "Drilled" not in context


def test_small_strata_are_taken_whole() -> None:
    items = draw_sample(LINES[:3], per_hazard=10, unflagged=10)
    assert len(items) == 3
    assert {i.weight for i in items} == {1.0}
    assert items[0].before or items[0].after


def test_sample_file_and_label_round_trip(tmp_path: Path) -> None:
    items = draw_sample(LINES, per_hazard=5, unflagged=5)
    sample = tmp_path / "sample.jsonl"
    write_sample(items, sample)
    rows = sample.read_text().splitlines()
    assert json.loads(rows[0])["header"]["sample_version"] == SAMPLE_VERSION
    assert len(rows) == 1 + len(items)

    labels = tmp_path / "labels.json"
    labels.write_text(
        json.dumps(
            {
                "sample_version": SAMPLE_VERSION,
                "labels": {
                    items[0].line.key: {
                        "hazards": ["LOST_CIRCULATION"],
                        "depth_m": 2010,
                        "unsure": False,
                    },
                    items[1].line.key: {"hazards": [], "depth_m": None, "unsure": True},
                },
            }
        )
    )
    read = read_labels(labels)
    assert read[items[0].line.key] == Label(frozenset({"LOST_CIRCULATION"}), 2010.0, False)
    assert read[items[1].line.key].unsure
    assert coverage(items, read)["unsure"] == 1

    labels.write_text(json.dumps({"sample_version": "gold-v0", "labels": {}}))
    with pytest.raises(ValueError, match="gold-v0"):
        read_labels(labels)
    labels.write_text(
        json.dumps({"sample_version": SAMPLE_VERSION, "labels": {"k": {"hazards": ["KICK"]}}})
    )
    with pytest.raises(ValueError, match="unknown hazards"):
        read_labels(labels)


def test_weighted_scores_match_hand_computation() -> None:
    items = draw_sample(LINES, per_hazard=10, unflagged=50)
    lc = [i for i in items if i.stratum == "LOST_CIRCULATION"]
    quiet = [i for i in items if i.stratum == UNFLAGGED_STRATUM]
    labels: dict[str, Label] = {}
    for i in lc[:8]:
        labels[i.line.key] = Label(frozenset({"LOST_CIRCULATION"}), None, False)  # true positives
    for i in lc[8:]:
        labels[i.line.key] = Label(frozenset(), None, False)  # false positives
    labels[quiet[0].line.key] = Label(frozenset({"LOST_CIRCULATION"}), None, False)  # a miss
    for i in quiet[1:]:
        labels[i.line.key] = Label(frozenset(), None, False)
    labels[quiet[1].line.key] = Label(frozenset({"STUCK_PIPE"}), None, True)  # unsure: ignored

    scores = score(items, labels, lambda ln: frozenset(ln.rule_hazards))
    s = scores["LOST_CIRCULATION"].summary()
    assert (s["tp"], s["fp"], s["fn"]) == (8, 2, 1)
    # Weighted: TP 8*3=24, FP 2*3=6, FN 1*10=10 → P 0.8, R 24/34.
    assert s["precision"] == 0.8
    assert s["recall"] == round(24 / 34, 3)
    assert "STUCK_PIPE" not in scores
    assert micro(scores).summary()["tp"] == 8


def test_rule_predictors_and_report(tmp_path: Path) -> None:
    predictors = rule_predictors()
    losses = line(
        1, "Observed losses of 10 m3/h at 2500 m.", code="interruption -- lost circulation"
    )
    assert predictors["codes"](losses) == {"LOST_CIRCULATION"}
    assert predictors["lexicon"](losses) == {"LOST_CIRCULATION"}
    assert predictors["rules"](line(2, "Drilled ahead.")) == frozenset()
    assert gold_report.rule_depth(losses, "LOST_CIRCULATION") == 2500.0
    assert gold_report.rule_depth(line(3, "x", md=None), "LOST_CIRCULATION") is None

    items = draw_sample(LINES, per_hazard=5, unflagged=5)
    labels = {i.line.key: Label(frozenset(i.line.rule_hazards), None, False) for i in items}
    payload = gold_report.build(items, labels, predictors)
    assert payload["tiers"]["lexicon"]["micro"]["precision"] == 1.0
    gold_report.write(payload, tmp_path)
    text = (tmp_path / "extraction_gold.md").read_text()
    assert "| lexicon |" in text
    assert (
        json.loads((tmp_path / "extraction_gold.json").read_text())["sample_version"]
        == SAMPLE_VERSION
    )
