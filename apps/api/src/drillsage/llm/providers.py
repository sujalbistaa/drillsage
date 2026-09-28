"""Model providers. Only `drillsage.llm.gateway` may use them (CLAUDE.md §5: single choke point)."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

import anthropic
from anthropic.types import MessageParam, TextBlockParam
from anthropic.types.beta.parsed_beta_message import ParsedBetaMessage
from anthropic.types.parsed_message import ParsedMessage
from pydantic import BaseModel

from drillsage.core.errors import DependencyUnavailableError, InvalidInputError
from drillsage.llm.pricing import TokenUsage

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"

type Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    output: dict[str, Any] | None
    """Schema-conforming JSON object; None when the model stopped without one."""
    stop_reason: str | None
    usage: TokenUsage
    served_model: str
    request_id: str | None
    refusal_category: str | None = None


class Provider(Protocol):
    name: str
    remote: bool

    async def complete_structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        effort: Effort,
        max_tokens: int,
    ) -> ProviderResponse: ...


def usage_from(usage: Any) -> TokenUsage:  # noqa: ANN401 - SDK Usage / BetaUsage share these fields
    return TokenUsage(
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
        cache_read_input_tokens=usage.cache_read_input_tokens or 0,
    )


class AnthropicProvider:
    """Claude via the official SDK: structured outputs, adaptive thinking, prompt caching.

    The system prompt carries a cache breakpoint, so the long, byte-stable extraction
    instructions are paid for once per cache lifetime rather than on every report.
    """

    name = "anthropic"
    remote = True

    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        *,
        refusal_fallback: bool = True,
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic(max_retries=4)
        self._refusal_fallback = refusal_fallback

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
        cached_system: list[TextBlockParam] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        messages: list[MessageParam] = [{"role": "user", "content": user}]
        try:
            if self._refusal_fallback:
                beta = await self._client.beta.messages.parse(
                    model=model,
                    max_tokens=max_tokens,
                    system=cached_system,
                    messages=messages,  # type: ignore[arg-type] # same wire shape as beta type
                    thinking={"type": "adaptive"},
                    output_config={"effort": effort},
                    output_format=schema,
                    betas=[REFUSAL_FALLBACK_BETA],
                    fallbacks="default",
                )
                return _response(beta)
            plain = await self._client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=cached_system,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                output_format=schema,
            )
            return _response(plain)
        except anthropic.BadRequestError as exc:
            raise InvalidInputError(f"model rejected the request: {exc.message}") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise DependencyUnavailableError(f"model credentials rejected: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise DependencyUnavailableError("model rate limit persisted after retries") from exc
        except anthropic.APIStatusError as exc:
            raise DependencyUnavailableError(f"model API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise DependencyUnavailableError("cannot reach the model API") from exc


def _response(message: ParsedMessage[BaseModel] | ParsedBetaMessage[BaseModel]) -> ProviderResponse:
    """Check `stop_reason` before trusting content: only a normal finish yields output."""
    parsed = message.parsed_output if message.stop_reason == "end_turn" else None
    stop_details = getattr(message, "stop_details", None)
    return ProviderResponse(
        output=parsed.model_dump(mode="json") if isinstance(parsed, BaseModel) else None,
        stop_reason=message.stop_reason,
        usage=usage_from(message.usage),
        served_model=message.model,
        request_id=message._request_id,
        refusal_category=getattr(stop_details, "category", None),
    )
