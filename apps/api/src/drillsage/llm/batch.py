"""Bulk backfill through the Message Batches API (50% of standard price).

Results arrive in any order and are keyed by `custom_id`, never by position. A batch keeps
running server-side if this process stops; pass its id as `resume_batch_id` to pick it up.
The same ledger, cache and local-only rules as the online gateway apply.
"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from pydantic import BaseModel, ValidationError

from drillsage.core.errors import BudgetExceededError, LocalOnlyViolationError
from drillsage.core.logging import get_logger
from drillsage.llm.gateway import cache_key
from drillsage.llm.pricing import cost_usd
from drillsage.llm.providers import Effort, usage_from
from drillsage.llm.store import CallRecord, LLMStore

log = get_logger(__name__)

POLL_SECONDS: Final = 30.0


@dataclass(frozen=True, slots=True)
class BatchItem:
    custom_id: str
    """`^[a-zA-Z0-9_-]{1,64}$`."""
    system: str
    user: str


@dataclass(frozen=True, slots=True)
class BatchOutcome:
    custom_id: str
    cache_key: str
    status: str
    """`ok`, `cached`, `refused`, `truncated`, `invalid`, `errored`, `expired` or `canceled`."""


def batch_params(
    item: BatchItem, *, model: str, schema: type[BaseModel], effort: Effort, max_tokens: int
) -> MessageCreateParamsNonStreaming:
    return MessageCreateParamsNonStreaming(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": item.system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": item.user}],
        thinking={"type": "adaptive"},
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)},
        },
    )


class BatchRunner:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        store: LLMStore,
        *,
        budget_usd: float,
        local_only: bool,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._store = store
        self._budget_usd = budget_usd
        self._local_only = local_only
        self._sleep = sleep

    async def run(
        self,
        *,
        purpose: str,
        model: str,
        prompt_version: str,
        items: Sequence[BatchItem],
        schema: type[BaseModel],
        effort: Effort,
        max_tokens: int,
        estimated_cost_usd: float,
        resume_batch_id: str | None = None,
    ) -> list[BatchOutcome]:
        if self._local_only:
            raise LocalOnlyViolationError("local-only mode forbids the remote Batches API")
        keys = {
            item.custom_id: cache_key(
                purpose=purpose,
                model=model,
                prompt_version=prompt_version,
                system=item.system,
                user=item.user,
            )
            for item in items
        }
        outcomes = [
            BatchOutcome(item.custom_id, keys[item.custom_id], "cached")
            for item in items
            if await self._store.get_result(keys[item.custom_id]) is not None
        ]
        cached = {o.custom_id for o in outcomes}
        pending = [item for item in items if item.custom_id not in cached]
        if not pending:
            return outcomes

        remaining = self._budget_usd - await self._store.spent_usd()
        if resume_batch_id is None and estimated_cost_usd > remaining:
            raise BudgetExceededError(
                f"estimated ${estimated_cost_usd:.2f} exceeds the remaining budget ${remaining:.2f}"
            )

        batch_id = resume_batch_id or await self._submit(
            pending, model=model, schema=schema, effort=effort, max_tokens=max_tokens
        )
        await self._wait(batch_id)
        outcomes.extend(
            await self._collect(
                batch_id,
                keys,
                purpose=purpose,
                model=model,
                prompt_version=prompt_version,
                schema=schema,
            )
        )
        return outcomes

    async def _submit(
        self,
        items: Sequence[BatchItem],
        *,
        model: str,
        schema: type[BaseModel],
        effort: Effort,
        max_tokens: int,
    ) -> str:
        requests = [
            Request(
                custom_id=item.custom_id,
                params=batch_params(
                    item, model=model, schema=schema, effort=effort, max_tokens=max_tokens
                ),
            )
            for item in items
        ]
        batch = await self._client.messages.batches.create(requests=requests)
        log.info("llm_batch_submitted", batch_id=batch.id, requests=len(requests))
        return batch.id

    async def _wait(self, batch_id: str) -> None:
        while True:
            batch = await self._client.messages.batches.retrieve(batch_id)
            if batch.processing_status == "ended":
                return
            log.info(
                "llm_batch_waiting",
                batch_id=batch_id,
                processing=batch.request_counts.processing,
                succeeded=batch.request_counts.succeeded,
            )
            await self._sleep(POLL_SECONDS)

    async def _collect(
        self,
        batch_id: str,
        keys: dict[str, str],
        *,
        purpose: str,
        model: str,
        prompt_version: str,
        schema: type[BaseModel],
    ) -> list[BatchOutcome]:
        outcomes: list[BatchOutcome] = []
        async for entry in await self._client.messages.batches.results(batch_id):
            key = keys.get(entry.custom_id)
            if key is None:
                log.warning("llm_batch_unknown_custom_id", custom_id=entry.custom_id)
                continue
            if entry.result.type != "succeeded":
                outcomes.append(BatchOutcome(entry.custom_id, key, entry.result.type))
                continue
            message = entry.result.message
            status, output = "ok", None
            if message.stop_reason == "refusal":
                status = "refused"
            elif message.stop_reason == "max_tokens":
                status = "truncated"
            else:
                text = next((b.text for b in message.content if b.type == "text"), "")
                try:
                    output = schema.model_validate_json(text)
                except ValidationError:
                    status = "invalid"
            usage = usage_from(message.usage)
            await self._store.record_call(
                CallRecord(
                    purpose=purpose,
                    provider="anthropic",
                    model=model,
                    served_model=message.model,
                    cache_key=key,
                    batch=True,
                    usage=usage,
                    cost_usd=cost_usd(usage, model, batch=True),
                    stop_reason=message.stop_reason,
                    status=status,
                    request_id=batch_id,
                )
            )
            if output is not None:
                await self._store.put_result(
                    key,
                    purpose=purpose,
                    model=model,
                    prompt_version=prompt_version,
                    output=output.model_dump(mode="json"),
                )
            outcomes.append(BatchOutcome(entry.custom_id, key, status))
        return outcomes
