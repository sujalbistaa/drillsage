"""Gold set: a stratified, hand-labelled sample of activities and the metrics computed from it.

Sampling design (so the numbers are honest estimates for the whole corpus, not just the sample):
- Every activity belongs to exactly one stratum: the first hazard the rule tier assigns to it,
  or `unflagged` when the rules find nothing.
- A fixed number is drawn at random from each stratum (seeded, so the sample is reproducible).
  Rare hazards therefore get enough examples to measure, and `unflagged` measures what the
  rules miss.
- Each labelled item carries the weight N_stratum / n_stratum. Precision, recall and F1 are
  computed from weighted counts (Horvitz-Thompson), so over-sampling rare hazards does not
  inflate them. Raw counts are reported alongside.

Items are keyed by `wellbore|report start|line` rather than database ids, so labels survive
rebuilding the database. Only keys and labels are committed; the text stays in `data/`.
"""

import json
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

from drillsage.domain.hazards import HazardType
from drillsage.extract.rules import HitSource, classify_activity
from drillsage.ingest.pipeline import ddr_paths
from drillsage.ingest.witsml_ddr import parse_ddr

SAMPLE_VERSION: Final = "gold-v1"
SAMPLE_SEED: Final = 20260928
PER_HAZARD: Final = 20
UNFLAGGED: Final = 120
UNFLAGGED_STRATUM: Final = "unflagged"


def activity_key(wellbore: str, report_start_iso: str, seq: int) -> str:
    return f"{wellbore}|{report_start_iso}|{seq}"


@dataclass(frozen=True, slots=True)
class Line:
    """One activity with the context a labeller needs."""

    key: str
    wellbore: str
    report_start: str
    seq: int
    start: str
    end: str
    md_m: float | None
    code: str | None
    state: str | None
    state_detail: str | None
    text: str
    rule_hazards: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GoldItem:
    line: Line
    stratum: str
    weight: float
    before: tuple[str, ...]
    after: tuple[str, ...]


def read_lines(data_dir: Path) -> list[Line]:
    """Every activity of every raw DDR, in report order, with the rule tier's hazards."""
    lines: list[Line] = []
    for path in ddr_paths(data_dir):
        for report in parse_ddr(path.read_bytes()).document.reports:
            if report.start_at is None:
                continue
            start = report.start_at.isoformat()
            for seq, activity in enumerate(report.activities):
                hits = classify_activity(
                    activity.proprietary_code, activity.state_detail, activity.comments
                )
                hazards = tuple(dict.fromkeys(h.hazard.value for h in hits))
                lines.append(
                    Line(
                        key=activity_key(report.wellbore_name, start, seq),
                        wellbore=report.wellbore_name,
                        report_start=start,
                        seq=seq,
                        start=activity.start_at.isoformat() if activity.start_at else "",
                        end=activity.end_at.isoformat() if activity.end_at else "",
                        md_m=activity.md_m,
                        code=activity.proprietary_code,
                        state=activity.state,
                        state_detail=activity.state_detail,
                        text=(activity.comments or "").strip(),
                        rule_hazards=hazards,
                    )
                )
    return lines


def stratum_of(line: Line) -> str:
    return line.rule_hazards[0] if line.rule_hazards else UNFLAGGED_STRATUM


def draw_sample(
    lines: Sequence[Line],
    *,
    per_hazard: int = PER_HAZARD,
    unflagged: int = UNFLAGGED,
    seed: int = SAMPLE_SEED,
    context: int = 2,
) -> list[GoldItem]:
    """Seeded stratified sample, each item with its weight and neighbouring lines."""
    index = {line.key: i for i, line in enumerate(lines)}
    strata: dict[str, list[Line]] = defaultdict(list)
    for line in lines:
        strata[stratum_of(line)].append(line)
    rng = random.Random(seed)  # noqa: S311 - sampling, not security
    items: list[GoldItem] = []
    for name in sorted(strata):
        population = strata[name]
        size = unflagged if name == UNFLAGGED_STRATUM else per_hazard
        chosen = rng.sample(population, min(size, len(population)))
        weight = len(population) / len(chosen)
        for line in chosen:
            i = index[line.key]
            same = [
                other
                for other in lines[max(0, i - context) : i + context + 1]
                if other.wellbore == line.wellbore and other.report_start == line.report_start
            ]
            items.append(
                GoldItem(
                    line=line,
                    stratum=name,
                    weight=round(weight, 6),
                    before=tuple(o.text for o in same if o.seq < line.seq),
                    after=tuple(o.text for o in same if o.seq > line.seq),
                )
            )
    rng.shuffle(items)  # labellers never see items grouped by stratum
    return items


def write_sample(items: Sequence[GoldItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        header = {"sample_version": SAMPLE_VERSION, "items": len(items), "seed": SAMPLE_SEED}
        out.write(json.dumps({"header": header}) + "\n")
        for item in items:
            out.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------------- labels


@dataclass(frozen=True, slots=True)
class Label:
    hazards: frozenset[str]
    depth_m: float | None
    unsure: bool


def read_labels(path: Path) -> dict[str, Label]:
    """Labels exported by `eval/labeling/label.html` (keys and labels only, no report text)."""
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("sample_version") != SAMPLE_VERSION:
        raise ValueError(f"labels are for {payload.get('sample_version')!r}, not {SAMPLE_VERSION}")
    valid = {h.value for h in HazardType}
    labels: dict[str, Label] = {}
    for key, raw in payload["labels"].items():
        hazards = frozenset(raw.get("hazards", []))
        unknown = hazards - valid
        if unknown:
            raise ValueError(f"{key}: unknown hazards {sorted(unknown)}")
        depth = raw.get("depth_m")
        labels[key] = Label(
            hazards, float(depth) if depth is not None else None, bool(raw.get("unsure"))
        )
    return labels


# ----------------------------------------------------------------------------- metrics


type Predictor = Callable[[Line], frozenset[str]]


def rule_predictors() -> dict[str, Predictor]:
    """The rule tier and its two halves, so the report shows what each contributes."""

    def by(sources: set[HitSource]) -> Predictor:
        def predict(line: Line) -> frozenset[str]:
            hits = classify_activity(line.code, line.state_detail, line.text)
            return frozenset(h.hazard.value for h in hits if h.source in sources)

        return predict

    return {
        "codes": by({HitSource.CODE}),
        "lexicon": by({HitSource.TEXT}),
        "rules": by({HitSource.CODE, HitSource.TEXT}),
    }


@dataclass
class HazardScore:
    tp: float = 0.0
    fp: float = 0.0
    fn: float = 0.0
    n_tp: int = 0
    n_fp: int = 0
    n_fn: int = 0
    depth_errors_m: list[float] = field(default_factory=list)

    def summary(self) -> dict[str, float | int | None]:
        precision = self.tp / (self.tp + self.fp) if self.tp + self.fp else None
        recall = self.tp / (self.tp + self.fn) if self.tp + self.fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else None
        )
        return {
            "precision": _r(precision),
            "recall": _r(recall),
            "f1": _r(f1),
            "tp": self.n_tp,
            "fp": self.n_fp,
            "fn": self.n_fn,
            "median_depth_error_m": (
                _r(statistics.median(self.depth_errors_m), 1) if self.depth_errors_m else None
            ),
        }


def _r(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def score(
    items: Iterable[GoldItem],
    labels: Mapping[str, Label],
    predictor: Predictor,
    depth_of: Callable[[Line, str], float | None] | None = None,
) -> dict[str, HazardScore]:
    """Weighted per-hazard confusion counts over labelled, confident items."""
    scores: dict[str, HazardScore] = defaultdict(HazardScore)
    for item in items:
        label = labels.get(item.line.key)
        if label is None or label.unsure:
            continue
        predicted = predictor(item.line)
        for hazard in label.hazards | predicted:
            s = scores[hazard]
            if hazard in label.hazards and hazard in predicted:
                s.tp += item.weight
                s.n_tp += 1
                if depth_of is not None and label.depth_m is not None:
                    guess = depth_of(item.line, hazard)
                    if guess is not None:
                        s.depth_errors_m.append(abs(guess - label.depth_m))
            elif hazard in predicted:
                s.fp += item.weight
                s.n_fp += 1
            else:
                s.fn += item.weight
                s.n_fn += 1
    return dict(scores)


def micro(scores: Mapping[str, HazardScore]) -> HazardScore:
    total = HazardScore()
    for s in scores.values():
        total.tp += s.tp
        total.fp += s.fp
        total.fn += s.fn
        total.n_tp += s.n_tp
        total.n_fp += s.n_fp
        total.n_fn += s.n_fn
        total.depth_errors_m.extend(s.depth_errors_m)
    return total


def coverage(items: Sequence[GoldItem], labels: Mapping[str, Label]) -> dict[str, Any]:
    """Counts for the report header (a JSON payload, hence the loose value type)."""
    labelled = [i for i in items if i.line.key in labels]
    return {
        "items": len(items),
        "labelled": len(labelled),
        "unsure": sum(1 for i in labelled if labels[i.line.key].unsure),
        "with_hazard": sum(1 for i in labelled if labels[i.line.key].hazards),
        "by_stratum": dict(Counter(i.stratum for i in labelled)),
    }
