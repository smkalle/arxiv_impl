# Repository Guidelines

## Project Structure & Module Organization

This repository is a multi-paper workspace; the active implementation is `ek_search/`, an Enterprise Knowledge Search prototype. Application code lives in `ek_search/app/`: API routes in `api.py`, service entry point in `main.py`, configuration in `config.py`, shared dataclasses/Pydantic models in `models.py`, vector persistence in `vector_store.py`, and backend, connector, ingestion, and eval code in their respective subpackages. Tests are in `ek_search/tests/`. Static dashboard assets are in `ek_search/dashboard/`, and sample/golden data is under `ek_search/data/`.

## Build, Test, and Development Commands

Run commands from `ek_search/`.

```bash
python3 -m pytest
```

Runs the full pytest suite using `pytest.ini`.

```bash
python3 -m pytest tests/test_api.py
```

Runs one focused test file.

```bash
python3 -m app.main
```

Starts the FastAPI app with settings from environment variables or `.env`.

```bash
uvicorn app.main:app --reload --port 8000
```

Runs the API during local development.

```bash
python3 scripts/generate_samples.py
```

Regenerates simple sample images for ingestion tests and demos.

## Coding Style & Naming Conventions

Use Python 3 with four-space indentation and type hints for public interfaces. Follow existing naming: modules and functions use `snake_case`, classes use `PascalCase`, and tests use `test_*`. Keep configuration in `app/config.py` and prefer existing abstractions such as `EmbeddingBackend`, connectors, preprocessors, and `ChromaVectorStore` over parallel implementations. There is no enforced formatter in the repo; keep imports tidy and changes consistent with nearby code.

## Testing Guidelines

The project uses `pytest`; discovery is configured in `ek_search/pytest.ini`. Add tests beside related coverage in `tests/`, with names like `test_vector_store.py` or `test_pipeline.py`. Prefer the `stub` embedding backend for deterministic unit tests. Mark expensive or network-dependent tests with `@pytest.mark.slow`, and do not require external API keys for the default test run.

## Commit & Pull Request Guidelines

Recent commits use concise imperative subjects, for example `Add sira kb ingestor package` and `Stop tracking generated SIRA artifacts`. Keep subjects short and behavior-focused. Pull requests should summarize the API, ingestion, backend, or dashboard behavior changed; list test commands run; call out new environment variables; and include screenshots for dashboard changes.

## Security & Configuration Tips

Copy `ek_search/.env.example` for local settings. Do not commit real `JINA_API_KEY` values or generated vector databases under `data/chroma`. Use `EMBEDDING_BACKEND=stub` for tests, `local` for offline development, and `jina_api` only when credentials are available.
