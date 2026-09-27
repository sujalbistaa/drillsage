# ADR 0001: A lean stack with one data store

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

DrillSage has to demo reliably on a student laptop (Apple M3, 16 GB RAM, about 6 GB free
disk), deploy on-premises for Oil India, and still look and behave like production
software. A rival team's public design uses PostGIS, MinIO, Qdrant, Kafka, Redis and
Celery. That is capable, but it is a lot of moving parts to operate, demo and explain.

## Decision

- **PostgreSQL 16 + pgvector is the only stateful service.** Relational data, full-text
  search (`tsvector`), vectors (`pgvector`) and the job queue (`SKIP LOCKED`) all live in
  it. Well-to-well distances are computed in Python (`pyproj`); a field has tens of wells,
  not millions, so PostGIS is unnecessary.
- **FastAPI + SQLAlchemy 2 (async) + Alembic** on Python 3.12, managed by `uv`.
- **Next.js 15 (App Router) + TypeScript strict + Tailwind 4.** The web client's types
  are generated from the API's OpenAPI schema; CI fails if they drift.
- **ONNX over torch** for local models (fastembed embeddings, RapidOCR), which keeps
  images and disk small.
- **Streaming via SSE** from pure-ASGI middleware (no `BaseHTTPMiddleware`, which buffers).

## Consequences

- `docker compose up` starts one container and a clean machine is demo-ready in minutes.
- One backup and restore story, and one security boundary to harden.
- If vector search ever outgrows pgvector (millions of chunks across all OIL fields), the
  retrieval module is the only code that changes. Its interface is kept store-agnostic.
