"""Structured output the LLM extractor must return (validated by the SDK and again by us).

Evidence is a verbatim quote plus the report line it came from; DrillSage, not the model,
computes the character offsets, so a quote that is not in the source is detected and dropped.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from drillsage.domain.hazards import HazardType


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Quote(_Out):
    line: int = Field(description="Number n of the activity line [n] the quote is taken from.")
    text: str = Field(
        description=(
            "Verbatim excerpt copied character for character from that line's text, "
            "at most about 200 characters, covering the words that show the problem or action."
        )
    )


class MitigationOut(_Out):
    action: str = Field(description="What the crew did, in a few words (e.g. 'Pumped LCM pill').")
    outcome: Literal["success", "failure", "unknown"] = Field(
        description="Whether the report says it worked; 'unknown' when the report does not say."
    )
    quote: Quote


class EventOut(_Out):
    hazard: HazardType
    subtype: str | None = Field(
        description=(
            "Short qualifier such as 'seepage', 'total losses', 'kick', 'pack-off'; null if none."
        )
    )
    evidence: list[Quote] = Field(
        description="One or more quotes proving the problem happened; required for every event."
    )
    md_top_m: float | None = Field(
        description=(
            "Shallowest measured depth (m) of the problem stated in the quoted text; "
            "null if not stated."
        )
    )
    md_bottom_m: float | None = Field(
        description=(
            "Deepest measured depth (m) of the problem stated in the quoted text; "
            "null if not stated."
        )
    )
    mitigations: list[MitigationOut]


class ReportExtraction(_Out):
    events: list[EventOut] = Field(
        description="Every distinct drilling problem experienced in this report; empty if none."
    )
