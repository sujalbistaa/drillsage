"""Gemini provider (Google AI Studio REST API) for the free-tier demo setup.

Free-tier capacity is uneven: models answer 503 "high demand" for minutes at a time, rate
limits answer 429, and older models are retired (404) for new keys. So every call:
- waits at least `min_interval_s` since the previous call (requests-per-minute limits);
- retries 429/500/503 with exponential backoff, honouring `Retry-After`;
- falls through a chain of models when one stays unavailable or is retired.

Structured output uses `responseMimeType: application/json` with the Pydantic JSON schema, and
the result is validated again by the gateway. The API key travels in the `x-goog-api-key`
header, never in the URL, and is never logged.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Final

import httpx
from pydantic import BaseModel, ValidationError

from drillsage.core.errors import DependencyUnavailableError, InvalidInputError
from drillsage.core.logging import get_logger
from drillsage.llm.pricing import TokenUsage
from drillsage.llm.providers import Effort, ProviderResponse

log = get_logger(__name__)

API_ROOT: Final = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE: Final = frozenset({429, 500, 503})
NEXT_MODEL: Final = frozenset({404})
MAX_ATTEMPTS_PER_MODEL: Final = 5
BASE_BACKOFF_S: Final = 2.0
MAX_BACKOFF_S: Final = 60.0

_FINISH_TO_STOP: Final = {
    "STOP": "end_turn",
    "MAX_TOKENS": "max_tokens",
    "SAFETY": "refusal",
    "RECITATION": "refusal",
    "BLOCKLIST": "refusal",
    "PROHIBITED_CONTENT": "refusal",
    "SPII": "refusal",
}
_THINKING_LEVEL: Final[dict[str, str]] = {
    "low": "low",
    "medium": "low",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}
"""Gemini 3.x exposes coarse thinking levels; `medium` maps down to keep free-tier calls fast."""


class GeminiProvider:
    name = "gemini"
    remote = True

    def __init__(
        self,
        api_key: str,
        *,
        fallback_models: Sequence[str] = (),
        min_interval_s: float = 0.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key:
            raise DependencyUnavailableError("GEMINI_API_KEY is not set")
        self._api_key = api_key
        self._fallbacks = tuple(fallback_models)
        self._min_interval_s = min_interval_s
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None

    async def _throttle(self) -> None:
        if self._last_call is not None:
            wait = self._min_interval_s - (self._clock() - self._last_call)
            if wait > 0:
                await self._sleep(wait)
        self._last_call = self._clock()

    def _body(
        self, system: str, user: str, schema: type[BaseModel], effort: Effort, max_tokens: int
    ) -> dict[str, Any]:
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema.model_json_schema(),
                "maxOutputTokens": max_tokens,
                "thinkingConfig": {"thinkingLevel": _THINKING_LEVEL[effort]},
            },
        }

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
        body = self._body(system, user, schema, effort, max_tokens)
        last_error = "no model tried"
        async with httpx.AsyncClient(transport=self._transport, timeout=180.0) as client:
            for candidate in (model, *self._fallbacks):
                for attempt in range(MAX_ATTEMPTS_PER_MODEL):
                    await self._throttle()
                    try:
                        response = await client.post(
                            f"{API_ROOT}/{candidate}:generateContent",
                            headers={"x-goog-api-key": self._api_key},
                            json=body,
                        )
                    except httpx.HTTPError as exc:
                        last_error = f"{candidate}: {type(exc).__name__}"
                        await self._sleep(_backoff(attempt, None))
                        continue
                    if response.status_code == 200:  # noqa: PLR2004
                        return _parse(response.json(), candidate, schema)
                    last_error = f"{candidate}: HTTP {response.status_code}"
                    if response.status_code in NEXT_MODEL:
                        break
                    if response.status_code not in RETRYABLE:
                        raise InvalidInputError(
                            f"Gemini rejected the request ({last_error}): {_message(response)}"
                        )
                    delay = _backoff(attempt, response.headers.get("retry-after"))
                    log.info(
                        "gemini_retry", model=candidate, status=response.status_code, wait_s=delay
                    )
                    await self._sleep(delay)
                log.warning("gemini_model_unavailable", model=candidate, reason=last_error)
        raise DependencyUnavailableError(f"no Gemini model answered ({last_error})")


def _backoff(attempt: int, retry_after: str | None) -> float:
    if retry_after is not None:
        try:
            return min(MAX_BACKOFF_S, float(retry_after))
        except ValueError:
            pass
    return min(MAX_BACKOFF_S, BASE_BACKOFF_S * 2.0**attempt)


def _message(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", {}).get("message", ""))[:200]
    except ValueError:
        return response.text[:200]


def _parse(payload: dict[str, Any], model: str, schema: type[BaseModel]) -> ProviderResponse:
    meta = payload.get("usageMetadata", {})
    usage = TokenUsage(
        input_tokens=int(meta.get("promptTokenCount", 0)),
        output_tokens=int(meta.get("candidatesTokenCount", 0))
        + int(meta.get("thoughtsTokenCount", 0)),
        cache_read_input_tokens=int(meta.get("cachedContentTokenCount", 0)),
    )
    served = str(payload.get("modelVersion") or model)
    request_id = payload.get("responseId")
    candidates = payload.get("candidates") or []
    if not candidates:
        block = payload.get("promptFeedback", {}).get("blockReason")
        return ProviderResponse(None, "refusal", usage, served, request_id, block)
    candidate = candidates[0]
    finish = str(candidate.get("finishReason", ""))
    stop = _FINISH_TO_STOP.get(finish, "other")
    output = None
    if stop == "end_turn":
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        try:
            output = schema.model_validate_json(text).model_dump(mode="json")
        except ValidationError:
            output = None
    category = finish.lower() if stop == "refusal" else None
    return ProviderResponse(output, stop, usage, served, request_id, category)
