"""Cost estimate shown to the user before any paid run (CLAUDE.md §5: explicit OK first).

Input tokens are estimated from characters; output tokens (adaptive thinking plus the JSON)
are the real unknown, so the estimate is a range. A small online pilot, which records exact
usage in the ledger, narrows it before a full backfill.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from drillsage.llm.pricing import BATCH_MULTIPLIER, CACHE_READ_MULTIPLIER, price_for

CHARS_PER_TOKEN: Final = 3.0
"""Conservative for upper-case technical English with many numbers (fewer chars per token)."""
OUTPUT_TOKENS_LOW: Final = 600
OUTPUT_TOKENS_HIGH: Final = 3_000


@dataclass(frozen=True, slots=True)
class CostEstimate:
    requests: int
    input_tokens: int
    system_tokens: int
    output_tokens_low: int
    output_tokens_high: int
    cost_low_usd: float
    cost_high_usd: float
    batch: bool
    model: str


def tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def estimate(
    system: str,
    users: Sequence[str],
    *,
    model: str,
    batch: bool,
    output_tokens_low: int = OUTPUT_TOKENS_LOW,
    output_tokens_high: int = OUTPUT_TOKENS_HIGH,
) -> CostEstimate:
    """Low: system prompt served from cache after the first request. High: never cached."""
    price = price_for(model)
    per_in = price.input_per_mtok / 1_000_000
    per_out = price.output_per_mtok / 1_000_000
    n = len(users)
    user_tokens = sum(tokens(u) for u in users)
    system_tokens = tokens(system)
    multiplier = BATCH_MULTIPLIER if batch else 1.0

    cached_system = system_tokens * (1 + max(0, n - 1) * CACHE_READ_MULTIPLIER)
    low = (user_tokens + cached_system) * per_in + n * output_tokens_low * per_out
    high = (user_tokens + n * system_tokens) * per_in + n * output_tokens_high * per_out
    return CostEstimate(
        requests=n,
        input_tokens=user_tokens,
        system_tokens=system_tokens,
        output_tokens_low=n * output_tokens_low,
        output_tokens_high=n * output_tokens_high,
        cost_low_usd=round(low * multiplier, 2),
        cost_high_usd=round(high * multiplier, 2),
        batch=batch,
        model=model,
    )
