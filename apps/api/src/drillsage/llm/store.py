"""Ledger and result cache behind one small interface (SQL in production, memory in tests)."""

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from drillsage.db import models as m
from drillsage.llm.pricing import TokenUsage


@dataclass(frozen=True, slots=True)
class CallRecord:
    purpose: str
    provider: str
    model: str
    served_model: str | None
    cache_key: str
    batch: bool
    usage: TokenUsage
    cost_usd: float
    stop_reason: str | None
    status: str
    request_id: str | None


class LLMStore(Protocol):
    async def spent_usd(self) -> float: ...

    async def record_call(self, record: CallRecord) -> None: ...

    async def get_result(self, cache_key: str) -> dict[str, Any] | None: ...

    async def put_result(
        self,
        cache_key: str,
        *,
        purpose: str,
        model: str,
        prompt_version: str,
        output: dict[str, Any],
    ) -> None: ...


class SqlLLMStore:
    """Writes are committed immediately: money spent must be recorded even if a later step fails."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def spent_usd(self) -> float:
        total = await self._session.scalar(select(func.coalesce(func.sum(m.LLMCall.cost_usd), 0.0)))
        return float(total or 0.0)

    async def record_call(self, record: CallRecord) -> None:
        self._session.add(
            m.LLMCall(
                purpose=record.purpose,
                provider=record.provider,
                model=record.model,
                served_model=record.served_model,
                cache_key=record.cache_key,
                batch=record.batch,
                input_tokens=record.usage.input_tokens,
                output_tokens=record.usage.output_tokens,
                cache_creation_input_tokens=record.usage.cache_creation_input_tokens,
                cache_read_input_tokens=record.usage.cache_read_input_tokens,
                cost_usd=record.cost_usd,
                stop_reason=record.stop_reason,
                status=record.status,
                request_id=record.request_id,
            )
        )
        await self._session.commit()

    async def get_result(self, cache_key: str) -> dict[str, Any] | None:
        row = await self._session.get(m.LLMResult, cache_key)
        return None if row is None else row.output

    async def put_result(
        self,
        cache_key: str,
        *,
        purpose: str,
        model: str,
        prompt_version: str,
        output: dict[str, Any],
    ) -> None:
        await self._session.execute(
            pg_insert(m.LLMResult)
            .values(
                cache_key=cache_key,
                purpose=purpose,
                model=model,
                prompt_version=prompt_version,
                output=output,
            )
            .on_conflict_do_nothing(index_elements=[m.LLMResult.cache_key])
        )
        await self._session.commit()


class MemoryLLMStore:
    """In-process store for tests and dry runs."""

    def __init__(self) -> None:
        self.calls: list[CallRecord] = []
        self.results: dict[str, dict[str, Any]] = {}

    async def spent_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    async def record_call(self, record: CallRecord) -> None:
        self.calls.append(record)

    async def get_result(self, cache_key: str) -> dict[str, Any] | None:
        return self.results.get(cache_key)

    async def put_result(
        self,
        cache_key: str,
        *,
        purpose: str,
        model: str,
        prompt_version: str,
        output: dict[str, Any],
    ) -> None:
        self.results.setdefault(cache_key, output)
