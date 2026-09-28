"""Locate a model's verbatim quote in the source comment and return its character span.

Exact match first. Models occasionally normalise whitespace or capitalisation, so a second
pass compares case-folded text with runs of whitespace collapsed, mapping the match back to
offsets in the original string. Anything else is a paraphrase and is rejected.
"""

import re

from drillsage.extract.rules import Span

_WS = re.compile(r"\s+")


def _normalised(text: str) -> tuple[str, list[int]]:
    """Case-folded text with whitespace runs collapsed, and each char's original index."""
    chars: list[str] = []
    index: list[int] = []
    previous_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if previous_space:
                continue
            chars.append(" ")
            previous_space = True
        else:
            chars.append(ch.casefold() if len(ch.casefold()) == 1 else ch.lower())
            previous_space = False
        index.append(i)
    return "".join(chars), index


def align_quote(source: str | None, quote: str) -> Span | None:
    if not source:
        return None
    needle = quote.strip()
    if not needle:
        return None
    position = source.find(needle)
    if position >= 0:
        return Span(position, position + len(needle))
    haystack, index = _normalised(source)
    target, _ = _normalised(needle)
    target = _WS.sub(" ", target).strip()
    position = haystack.find(target)
    if position < 0:
        return None
    start = index[position]
    end = index[position + len(target) - 1] + 1
    return Span(start, end)
