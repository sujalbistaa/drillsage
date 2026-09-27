# DrillSage

*Drishti (foresight) for every well you drill.*

DrillSage is a Nearby Wells Intelligence System for **Oil India Limited** (Smart India
Hackathon 2026, problem statement **SIH26121**). It reads historical daily drilling reports,
extracts every drilling problem with the exact depth, formation and fix, and warns the
engineer on the active well **before** the bit reaches a zone where nearby wells had
trouble. Every warning links to the report line behind it.

> Status: **Phase 1 (data and canonical model)** complete. See the phase plan in [CLAUDE.md](CLAUDE.md#8-phase-plan-work-phase-by-phase-stop-at-every-gate-for-user-review).

## Quick start

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), Node 22+ with pnpm 9.

```bash
make setup     # dependencies + git hooks (creates .env from .env.example)
make dev       # Postgres + API on :8000 + web on :3000
make test      # API + web tests
make lint      # ruff, mypy --strict, eslint, tsc, prettier
make help      # everything else
```

Open http://localhost:3000. The API's interactive docs are at http://localhost:8000/docs.

### Load the data

```bash
make data      # fetch (pinned + checksummed) → load Postgres → write data reports
```

`make data` downloads the Volve daily drilling reports (1,380 WITSML files, pinned to one
commit and verified by SHA-256) and the Norwegian Offshore Directorate's wellbore and
lithostratigraphy tables into `data/raw/`, then loads them into Postgres. It is idempotent:
running it again changes nothing. It writes two reports:

- [`eval/reports/parser_fidelity.md`](eval/reports/parser_fidelity.md): every one of the
  245,516 values in the source reports is accounted for.
- [`eval/reports/data_qc.md`](eval/reports/data_qc.md): per-wellbore coverage, trajectory
  quality and formation tops, with trajectories checked against the regulator's final TVDs.

How the data is modelled and cleaned is described in [docs/data-pipeline.md](docs/data-pipeline.md).

## Repository layout

| Path | What |
|---|---|
| `apps/api` | FastAPI service (Python 3.12): ingestion, extraction, knowledge, risk engine |
| `apps/web` | Next.js 15 web app: field map, well cockpit, alerts, cited Q&A |
| `infra` | Docker Compose (Postgres 16 + pgvector) |
| `eval` | Evaluation harness and generated metric reports |
| `docs` | Architecture decisions and domain primer |
| `research` | SIH 2026 problem-statement research |

## Data and licence

Contains data from the Volve field dataset, released by Equinor and the Volve licence
partners under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
Volve data and anything derived from it may be used for non-commercial purposes only, with
attribution, under the same licence. Raw data is never committed to this repository.

Wellbore coordinates and lithostratigraphy come from the Norwegian Offshore Directorate
(Sodir) FactPages, published under the Norwegian Licence for Open Government Data (NLOD).
