from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI

from sira_kb_ingestor.api import create_app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    workers: int = 4,
    artifact_dir: Path | str = "./sira-artifacts",
) -> None:
    app = create_app(artifact_dir=artifact_dir)
    uvicorn.run(app, host=host, port=port, workers=workers)


__all__ = ["FastAPI", "create_app", "run_server"]
