"""List prices and cost accounting for the budget ledger.

Prices are USD per million tokens (Anthropic first-party API). Cache writes (5-minute TTL)
bill at 1.25x input, cache reads at 0.1x input, and the Message Batches API halves every
token price. Update this table when prices change; the ledger stores the computed cost of
each call at the time it was made.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float


PRICES: Final[dict[str, ModelPrice]] = {
    "claude-fable-5-1": ModelPrice(10.0, 50.0),
    "claude-opus-5-5": ModelPrice(4.0, 20.0),
    "claude-opus-5": ModelPrice(5.0, 25.0),
    "claude-opus-4-8": ModelPrice(5.0, 25.0),
    "claude-sonnet-5": ModelPrice(2.0, 10.0),
    "claude-haiku-4-5": ModelPrice(1.0, 5.0),
}
CACHE_WRITE_MULTIPLIER: Final = 1.25
CACHE_READ_MULTIPLIER: Final = 0.1
BATCH_MULTIPLIER: Final = 0.5


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


FREE_TIER: Final = ModelPrice(0.0, 0.0)
"""Gemini through a Google AI Studio free-tier key. Paid-tier Gemini prices are not zero; add
explicit entries above if a paid key is used."""


def price_for(model: str) -> ModelPrice:
    if model in PRICES:
        return PRICES[model]
    if model.startswith("gemini-"):
        return FREE_TIER
    raise KeyError(f"no price for model {model!r}; add it to drillsage.llm.pricing")


def cost_usd(usage: TokenUsage, model: str, *, batch: bool = False) -> float:
    price = price_for(model)
    per_input = price.input_per_mtok / 1_000_000
    cost = (
        usage.input_tokens * per_input
        + usage.cache_creation_input_tokens * per_input * CACHE_WRITE_MULTIPLIER
        + usage.cache_read_input_tokens * per_input * CACHE_READ_MULTIPLIER
        + usage.output_tokens * price.output_per_mtok / 1_000_000
    )
    return cost * (BATCH_MULTIPLIER if batch else 1.0)
