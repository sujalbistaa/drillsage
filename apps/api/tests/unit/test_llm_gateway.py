"""LLM gateway, pricing and estimates. No test here calls a live model (CLAUDE.md §5)."""

from dataclasses import dataclass, field, replace
from typing import Any

import pytest
from pydantic import BaseModel

from drillsage.core.errors import BudgetExceededError, LLMOutputError, LocalOnlyViolationError
from drillsage.llm.estimate import estimate, tokens
from drillsage.llm.gateway import LLMGateway, cache_key
from drillsage.llm.pricing import TokenUsage, cost_usd, price_for
from drillsage.llm.providers import Effort, ProviderResponse, _response
from drillsage.llm.store import MemoryLLMStore


class Answer(BaseModel):
    value: int


@dataclass
class FakeProvider:
    responses: list[ProviderResponse]
    name: str = "fake"
    remote: bool = True
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def complete_structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        effort: Effort,
        max_tokens: int,
    ) -> ProviderResponse:
        self.calls.append({"model": model, "user": user, "effort": effort})
        return self.responses.pop(0)


USAGE = TokenUsage(input_tokens=1_000, output_tokens=500, cache_read_input_tokens=2_000)


def ok(value: int = 7) -> ProviderResponse:
    return ProviderResponse({"value": value}, "end_turn", USAGE, "claude-opus-5", "req_1")


def gateway(provider: FakeProvider, store: MemoryLLMStore, **kw: Any) -> LLMGateway:
    return LLMGateway(
        provider, store, budget_usd=kw.get("budget", 10.0), local_only=kw.get("local", False)
    )


async def ask(gw: LLMGateway, user: str = "q") -> Any:
    return await gw.structured(
        purpose="extract",
        model="claude-opus-5",
        prompt_version="p1",
        system="sys",
        user=user,
        schema=Answer,
        effort="medium",
        max_tokens=1000,
    )


async def test_first_call_is_paid_and_recorded_then_cached_for_free() -> None:
    provider, store = FakeProvider([ok()]), MemoryLLMStore()
    gw = gateway(provider, store)
    first = await ask(gw)
    assert first.output == Answer(value=7)
    assert not first.cached
    assert first.cost_usd == pytest.approx(1_000 * 5e-6 + 2_000 * 5e-6 * 0.1 + 500 * 25e-6)
    assert [c.status for c in store.calls] == ["ok"]
    assert store.calls[0].request_id == "req_1"

    again = await ask(gw)
    assert again.cached
    assert again.cost_usd == 0
    assert len(provider.calls) == 1
    assert len(store.calls) == 1


async def test_local_only_fails_closed_before_any_call() -> None:
    provider = FakeProvider([ok()])
    with pytest.raises(LocalOnlyViolationError):
        await ask(gateway(provider, MemoryLLMStore(), local=True))
    assert provider.calls == []


async def test_budget_cap_stops_new_calls_but_not_cached_ones() -> None:
    store = MemoryLLMStore()
    gw = gateway(FakeProvider([ok()]), store, budget=0.02)
    await ask(gw, "a")  # costs ~$0.018 and leaves ~$0.002
    await ask(gw, "a")  # cached: allowed
    store.calls[0] = replace(store.calls[0], cost_usd=0.02)  # spend exactly the cap
    with pytest.raises(BudgetExceededError):
        await ask(gw, "b")


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (ProviderResponse(None, "refusal", USAGE, "claude-opus-5", "r", "cyber"), "refused"),
        (ProviderResponse(None, "max_tokens", USAGE, "claude-opus-5", "r"), "truncated"),
        (
            ProviderResponse({"value": "not a number"}, "end_turn", USAGE, "claude-opus-5", "r"),
            "invalid",
        ),
        (ProviderResponse(None, "end_turn", USAGE, "claude-opus-5", "r"), "invalid"),
    ],
)
async def test_unusable_output_is_paid_for_recorded_and_raised(
    response: ProviderResponse, status: str
) -> None:
    store = MemoryLLMStore()
    with pytest.raises(LLMOutputError, match=status):
        await ask(gateway(FakeProvider([response]), store))
    assert [c.status for c in store.calls] == [status]
    assert store.calls[0].cost_usd > 0
    assert store.results == {}


def test_cache_key_covers_everything_that_changes_the_output() -> None:
    base = {"purpose": "extract", "model": "m", "prompt_version": "p", "system": "s", "user": "u"}
    key = cache_key(**base)
    assert key == cache_key(**base)
    for field_name in base:
        assert cache_key(**{**base, field_name: "changed"}) != key


def test_pricing() -> None:
    assert price_for("claude-opus-5").input_per_mtok == 5.0
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost_usd(usage, "claude-opus-5") == pytest.approx(30.0)
    assert cost_usd(usage, "claude-opus-5", batch=True) == pytest.approx(15.0)
    writes = TokenUsage(cache_creation_input_tokens=1_000_000)
    assert cost_usd(writes, "claude-opus-5") == pytest.approx(6.25)
    with pytest.raises(KeyError, match="no price"):
        price_for("gpt-5")


def test_estimate_is_a_range_and_batch_halves_it() -> None:
    assert tokens("x" * 30) == 10
    online = estimate("s" * 3000, ["u" * 3000] * 10, model="claude-opus-5", batch=False)
    batch = estimate("s" * 3000, ["u" * 3000] * 10, model="claude-opus-5", batch=True)
    assert online.cost_low_usd < online.cost_high_usd
    assert batch.cost_high_usd == pytest.approx(online.cost_high_usd / 2, abs=0.01)
    assert online.requests == 10
    assert online.system_tokens == 1000


@dataclass
class _Stop:
    category: str | None


@dataclass
class _Usage:
    input_tokens: int = 10
    output_tokens: int = 5
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = 3


@dataclass
class _Message:
    stop_reason: str
    parsed_output: BaseModel | None
    stop_details: _Stop | None = None
    usage: _Usage = field(default_factory=_Usage)
    model: str = "claude-opus-5"
    _request_id: str = "req_x"


def test_provider_reads_stop_reason_before_content() -> None:
    done = _response(_Message("end_turn", Answer(value=3)))  # type: ignore[arg-type]
    assert done.output == {"value": 3}
    assert done.usage == TokenUsage(10, 5, 0, 3)
    refused = _response(_Message("refusal", Answer(value=3), _Stop("cyber")))  # type: ignore[arg-type]
    assert refused.output is None
    assert refused.refusal_category == "cyber"
    cut = _response(_Message("max_tokens", Answer(value=3)))  # type: ignore[arg-type]
    assert cut.output is None
