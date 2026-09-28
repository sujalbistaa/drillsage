"""Rule layer: turn one activity (code, state, comment) into hazard hits with evidence spans.

Pure functions, no I/O. A span is a half-open character range into the activity's `comments`
exactly as stored, so evidence always resolves back to the source text.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from drillsage.domain.hazards import HazardType
from drillsage.extract.lexicon import (
    CODE_RULES,
    MITIGATION_RULES,
    NEGATION,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    TEXT_RULES,
)

RULES_VERSION: Final = "rules-1.0.0"

_SENTENCE_END = re.compile(r"[;\n!?]|\.(?=\s|$)")
_DEPTH = re.compile(
    r"(?<![\d.,])(\d{2,5}(?:[.,]\d{1,2})?)\s?m(?:d|etres?|eters?|tr)?\b(?![\s-]*(?:tvd|3|³))",
    re.IGNORECASE,
)
_NEGATION_WINDOW = 40


class HitSource(StrEnum):
    CODE = "code"
    TEXT = "text"
    LLM = "llm"


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int

    def of(self, text: str) -> str:
        return text[self.start : self.end]


@dataclass(frozen=True, slots=True)
class Hit:
    hazard: HazardType
    rule_id: str
    source: HitSource
    span: Span | None
    """Trigger phrase in the comment; None for code-only hits."""
    subtype: str | None
    depths_m: tuple[float, ...]
    """Depths (MD, metres) stated in the trigger's sentence."""


@dataclass(frozen=True, slots=True)
class MitigationHit:
    rule_id: str
    action: str
    span: Span
    hazards: frozenset[HazardType]


@dataclass(frozen=True, slots=True)
class OutcomeHit:
    success: bool
    span: Span


def sentence_bounds(text: str, position: int) -> Span:
    """The sentence containing `position` (decimal points like `1.55` do not end sentences)."""
    start = 0
    for match in _SENTENCE_END.finditer(text, 0, position):
        start = match.end()
    following = _SENTENCE_END.search(text, position)
    end = following.start() if following else len(text)
    return Span(start, end)


def depths_in(text: str, span: Span) -> tuple[float, ...]:
    """Measured depths in metres mentioned inside `span` (`3010 m`, `3087M`, `2707 m MD`)."""
    return tuple(
        float(match.group(1).replace(",", "."))
        for match in _DEPTH.finditer(text, span.start, span.end)
    )


def _negated(text: str, sentence: Span, start: int) -> bool:
    window_start = max(sentence.start, start - _NEGATION_WINDOW)
    return NEGATION.search(text[window_start:start]) is not None


def code_hits(proprietary_code: str | None, state_detail: str | None) -> list[Hit]:
    hits = []
    for rule in CODE_RULES:
        code_ok = rule.proprietary_code is None or rule.proprietary_code == proprietary_code
        detail_ok = rule.state_detail is None or rule.state_detail == state_detail
        if code_ok and detail_ok:
            hits.append(Hit(rule.hazard, rule.id, HitSource.CODE, None, rule.subtype, ()))
    return hits


def text_hits(comments: str | None) -> list[Hit]:
    if not comments:
        return []
    hits = []
    for rule in TEXT_RULES:
        for match in rule.pattern.finditer(comments):
            sentence = sentence_bounds(comments, match.start())
            text = sentence.of(comments)
            if rule.exclude is not None and rule.exclude.search(text):
                continue
            if rule.require is not None and not rule.require.search(text):
                continue
            if _negated(comments, sentence, match.start()):
                continue
            hits.append(
                Hit(
                    hazard=rule.hazard,
                    rule_id=rule.id,
                    source=HitSource.TEXT,
                    span=Span(match.start(), match.end()),
                    subtype=rule.subtype,
                    depths_m=depths_in(comments, sentence),
                )
            )
    return hits


def classify_activity(
    proprietary_code: str | None, state_detail: str | None, comments: str | None
) -> list[Hit]:
    """All hazard hits for one activity: code rules first, then text rules in text order."""
    text = sorted(text_hits(comments), key=lambda h: (h.span.start if h.span else 0, h.rule_id))
    return [*code_hits(proprietary_code, state_detail), *text]


def mitigation_hits(comments: str | None) -> Iterator[MitigationHit]:
    if not comments:
        return
    for rule in MITIGATION_RULES:
        for match in rule.pattern.finditer(comments):
            sentence = sentence_bounds(comments, match.start())
            if _negated(comments, sentence, match.start()):
                continue
            yield MitigationHit(
                rule.id, rule.action, Span(match.start(), match.end()), rule.hazards
            )


def outcome_hits(comments: str | None) -> Iterator[OutcomeHit]:
    if not comments:
        return
    for success, pattern in ((True, OUTCOME_SUCCESS), (False, OUTCOME_FAILURE)):
        for match in pattern.finditer(comments):
            yield OutcomeHit(success, Span(match.start(), match.end()))
