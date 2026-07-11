"""FastAPI app entrypoint. Run with `python -m metaorch` or `uvicorn metaorch.api.main:app`."""

from __future__ import annotations

import sys

from fastapi import FastAPI

from metaorch import __version__
from metaorch.api.routes import router
from metaorch.config import load_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="metaorch",
        version=__version__,
        description=(
            "Meta-orchestrator pipeline chaining all arxiv_impl subprojects' use cases "
            "end-to-end: ingest → kb enrich → retrieve (SIRA/TicketMind/Jina) → "
            "catalog enrich → evolve (EvolveMem) → coevolve (RGQM)."
        ),
    )
    app.include_router(router)
    return app


app = create_app()


def cli() -> int:
    """Console entry: `metaorch` — runs uvicorn against the configured host/port."""
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "metaorch.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli())