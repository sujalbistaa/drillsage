# DrillSage API

FastAPI service for DrillSage (SIH26121). The architecture, standards and phase plan are in
the repository's `CLAUDE.md`. Everyday commands go through the root `Makefile`.

```bash
uv sync                                                    # install (Python 3.12)
uv run uvicorn drillsage.api.app:create_app --factory --reload
uv run pytest                                              # unit + integration (skipped without DB)
uv run alembic upgrade head                                # migrate
```
