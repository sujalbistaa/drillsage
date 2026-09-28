"""Gemini provider against a mock transport (no network, no key needed)."""

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from drillsage.core.config import Environment, Settings
from drillsage.core.errors import DependencyUnavailableError, InvalidInputError
from drillsage.llm.factory import make_provider
from drillsage.llm.gemini import GeminiProvider
from drillsage.llm.pricing import TokenUsage, cost_usd
from drillsage.llm.providers import AnthropicProvider

KEY = "test-key-not-real"


class Answer(BaseModel):
    value: int


def ok(value: int = 3, *, finish: str = "STOP", text: str | None = None) -> dict[str, Any]:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "thinking...", "thought": True},
                        {"text": text if text is not None else json.dumps({"value": value})},
                    ]
                },
                "finishReason": finish,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 900,
            "candidatesTokenCount": 40,
            "thoughtsTokenCount": 60,
            "cachedContentTokenCount": 0,
        },
        "modelVersion": "gemini-3.8-flash-001",
        "responseId": "resp_1",
    }


class Script:
    """Replays scripted (status, body, headers) per model and records every request."""

    def __init__(self, plan: dict[str, list[tuple[int, dict[str, Any], dict[str, str]]]]) -> None:
        self.plan = plan
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        model = request.url.path.rsplit("/", 1)[-1].split(":")[0]
        status, body, headers = self.plan[model].pop(0)
        return httpx.Response(status, json=body, headers=headers)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def provider(script: Script, clock: Clock, **kw: Any) -> GeminiProvider:
    return GeminiProvider(
        KEY,
        fallback_models=kw.get("fallbacks", ("gemini-lite",)),
        min_interval_s=kw.get("interval", 0.0),
        transport=httpx.MockTransport(script),
        sleep=clock.sleep,
        clock=clock,
    )


async def call(p: GeminiProvider, effort: str = "medium") -> Any:
    return await p.complete_structured(
        model="gemini-3.8-flash",
        system="sys",
        user="report",
        schema=Answer,
        effort=effort,  # type: ignore[arg-type]
        max_tokens=1000,
    )


BUSY: tuple[int, dict[str, Any], dict[str, str]] = (503, {"error": {"message": "high demand"}}, {})


async def test_success_skips_thought_parts_and_counts_thinking_as_output() -> None:
    script, clock = Script({"gemini-3.8-flash": [(200, ok(), {})]}), Clock()
    response = await call(provider(script, clock))
    assert response.output == {"value": 3}
    assert response.stop_reason == "end_turn"
    assert response.usage == TokenUsage(input_tokens=900, output_tokens=100)
    assert (response.served_model, response.request_id) == ("gemini-3.8-flash-001", "resp_1")
    request = script.requests[0]
    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in str(request.url)
    body = json.loads(request.content)
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["properties"]["value"]["type"] == "integer"
    assert config["thinkingConfig"] == {"thinkingLevel": "low"}
    assert body["systemInstruction"]["parts"][0]["text"] == "sys"


async def test_busy_model_is_retried_with_backoff_then_answers() -> None:
    script = Script({"gemini-3.8-flash": [BUSY, (429, {}, {"retry-after": "7"}), (200, ok(), {})]})
    clock = Clock()
    response = await call(provider(script, clock))
    assert response.output == {"value": 3}
    assert clock.sleeps == [2.0, 7.0]


async def test_falls_through_to_next_model_when_primary_stays_busy_or_retired() -> None:
    script = Script({"gemini-3.8-flash": [BUSY] * 5, "gemini-lite": [(200, ok(9), {})]})
    response = await call(provider(script, Clock()))
    assert response.output == {"value": 9}
    assert len(script.requests) == 6

    retired = Script({"gemini-3.8-flash": [(404, {}, {})], "gemini-lite": [(200, ok(), {})]})
    assert (await call(provider(retired, Clock()))).output == {"value": 3}
    assert len(retired.requests) == 2


async def test_all_models_unavailable_raises() -> None:
    script = Script({"gemini-3.8-flash": [BUSY] * 5, "gemini-lite": [BUSY] * 5})
    with pytest.raises(DependencyUnavailableError, match="no Gemini model answered"):
        await call(provider(script, Clock()))


async def test_bad_request_is_not_retried() -> None:
    script = Script({"gemini-3.8-flash": [(400, {"error": {"message": "bad schema"}}, {})]})
    with pytest.raises(InvalidInputError, match="bad schema"):
        await call(provider(script, Clock()))
    assert len(script.requests) == 1


@pytest.mark.parametrize(
    ("payload", "stop", "category"),
    [
        (ok(finish="MAX_TOKENS"), "max_tokens", None),
        (ok(finish="SAFETY"), "refusal", "safety"),
        ({"promptFeedback": {"blockReason": "OTHER"}, "usageMetadata": {}}, "refusal", "OTHER"),
        (ok(text="not json"), "end_turn", None),
    ],
)
async def test_non_answers_carry_no_output(
    payload: dict[str, Any], stop: str, category: str | None
) -> None:
    script = Script({"gemini-3.8-flash": [(200, payload, {})]})
    response = await call(provider(script, Clock()))
    assert response.output is None
    assert response.stop_reason == stop
    assert response.refusal_category == category


async def test_min_interval_throttles_consecutive_calls() -> None:
    script = Script({"gemini-3.8-flash": [(200, ok(), {}), (200, ok(), {})]})
    clock = Clock()
    p = provider(script, clock, interval=6.0)
    await call(p)
    clock.now += 1.5
    await call(p, effort="high")
    assert clock.sleeps == [pytest.approx(4.5)]
    assert json.loads(script.requests[1].content)["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "high"
    }


def test_factory_and_free_tier_pricing() -> None:
    gemini = Settings(
        environment=Environment.TEST,
        llm_provider="gemini",
        GEMINI_API_KEY=SecretStr("k"),
        _env_file=None,
    )
    assert isinstance(make_provider(gemini), GeminiProvider)
    missing = Settings(environment=Environment.TEST, llm_provider="gemini", _env_file=None)
    with pytest.raises(DependencyUnavailableError, match="GEMINI_API_KEY"):
        make_provider(missing)
    claude = Settings(environment=Environment.TEST, llm_provider="anthropic", _env_file=None)
    assert isinstance(make_provider(claude), AnthropicProvider)
    assert cost_usd(TokenUsage(input_tokens=10**6, output_tokens=10**6), "gemini-3.8-flash") == 0.0
