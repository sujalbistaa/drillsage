"""The single choke point for every model call (CLAUDE.md §5).

In order, every call:
1. fails closed when local-only mode forbids the provider;
2. returns a cached result when the same model, prompt version and input were seen before
   (re-ingesting costs nothing);
3. refuses when the budget cap is already reached;
4. calls the provider, then records model, tokens, cost, stop reason and request id;
5. accepts output only when the model finished normally and the output validates.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ValidationError

from drillsage.core.errors import BudgetExceededError, LLMOutputError, LocalOnlyViolationError
from drillsage.core.logging import get_logger
from drillsage.llm.pricing import cost_usd
from drillsage.llm.providers import Effort, Provider, ProviderResponse
from drillsage.llm.store import CallRecord, LLMStore

log = get_logger(__name__)

_KEY_VERSION: Final = "v1"


def cache_key(*, purpose: str, model: str, prompt_version: str, system: str, user: str) -> str:
    """Content hash of everything that determines the output."""
    payload = json.dumps(
        [_KEY_VERSION, purpose, model, prompt_version, system, user],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GatewayResult[T: BaseModel]:
    output: T
    cache_key: str
    cached: bool
    cost_usd: float


def _status(response: ProviderResponse) -> str:
    if response.stop_reason == "refusal":
        return "refused"
    if response.stop_reason == "max_tokens":
        return "truncated"
    if response.output is None:
        return "invalid"
    return "ok"


class LLMGateway:
    def __init__(
        self,
        provider: Provider,
        store: LLMStore,
        *,
        budget_usd: float,
        local_only: bool,
    ) -> None:
        self._provider = provider
        self._store = store
        self._budget_usd = budget_usd
        self._local_only = local_only

    def _check_local_only(self) -> None:
        if self._local_only and self._provider.remote:
            raise LocalOnlyViolationError(
                f"local-only mode forbids calls to the remote provider {self._provider.name!r}"
            )

    async def remaining_budget_usd(self) -> float:
        return max(0.0, self._budget_usd - await self._store.spent_usd())

    async def structured(
        self,
        *,
        purpose: str,
        model: str,
        prompt_version: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        effort: Effort,
        max_tokens: int,
    ) -> GatewayResult[BaseModel]:
        self._check_local_only()
        key = cache_key(
            purpose=purpose, model=model, prompt_version=prompt_version, system=system, user=user
        )
        cached = await self._store.get_result(key)
        if cached is not None:
            return GatewayResult(schema.model_validate(cached), key, cached=True, cost_usd=0.0)

        if await self.remaining_budget_usd() <= 0:
            raise BudgetExceededError(f"LLM budget of ${self._budget_usd:.2f} is spent")

        response = await self._provider.complete_structured(
            model=model,
            system=system,
            user=user,
            schema=schema,
            effort=effort,
            max_tokens=max_tokens,
        )
        status = _status(response)
        output: BaseModel | None = None
        if status == "ok":
            try:
                output = schema.model_validate(response.output)
            except ValidationError:
                status = "invalid"
        cost = cost_usd(response.usage, model)
        await self._store.record_call(
            CallRecord(
                purpose=purpose,
                provider=self._provider.name,
                model=model,
                served_model=response.served_model,
                cache_key=key,
                batch=False,
                usage=response.usage,
                cost_usd=cost,
                stop_reason=response.stop_reason,
                status=status,
                request_id=response.request_id,
            )
        )
        log.info(
            "llm_call",
            purpose=purpose,
            model=model,
            served_model=response.served_model,
            status=status,
            cost_usd=round(cost, 5),
            cache_read_input_tokens=response.usage.cache_read_input_tokens,
            request_id=response.request_id,
        )
        if output is None:
            detail = f" ({response.refusal_category})" if response.refusal_category else ""
            raise LLMOutputError(f"{purpose}: model output not usable: {status}{detail}")
        await self._store.put_result(
            key,
            purpose=purpose,
            model=model,
            prompt_version=prompt_version,
            output=output.model_dump(mode="json"),
        )
        return GatewayResult(output, key, cached=False, cost_usd=cost)
