# DrillSage API

FastAPI service for DrillSage (SIH26121). Design notes are in the repository's `docs/`;
everyday commands go through the root `Makefile`.

```bash
uv sync                                                    # install (Python 3.12)
uv run uvicorn drillsage.api.app:create_app --factory --reload
uv run pytest                                              # unit + integration (skipped without DB)
uv run alembic upgrade head                                # migrate
```
