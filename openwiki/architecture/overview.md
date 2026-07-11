# Architecture overview

This repository is organized as a set of self-contained implementation workspaces, each one corresponding to a different arXiv paper or paper-derived product prototype. There is no root-level application or shared runtime. That design matters because most commands, test fixtures, data paths, and generated artifacts are local to a single subproject.

## Repository shape

At a high level:

- `sira/` implements a retrieval system for support tickets and knowledge-base articles.
- `AAFLOW-2605.02162/` implements an Arrow-native ingest pipeline for ticket data.
- `sira-kb-ingestor/` stitches those two ideas together into a packaged setup/query/server workflow.
- `datamaster/` contains the CatalogAgent/DataMaster implementation for autonomous catalog enrichment.
- `jina-2605.08384/`, `tkmem-2605.13941/`, and `rgqm/` are additional paper workspaces with their own local documentation and status.

The root `README.md` is a table of contents, but the authoritative operational guidance usually lives in each subproject's own `AGENTS.md`, `CLAUDE.md`, `README.md`, and `pyproject.toml`.

## Common conventions

### 1. Work inside the target subproject

Subprojects assume relative paths and local runtime artifacts. Example consequences:

- SIRA commands are run from `sira/`.
- CatalogAgent commands are run from `datamaster/catalog-agent/`.
- `sira-kb-ingestor` commands are run from `sira-kb-ingestor/`.

### 2. Use `python3`

The root guidance explicitly says `python` may not exist. All documented commands use `python3`.

### 3. Treat generated artifacts as local

Each project has its own output contract and artifact hygiene rules. Examples:

- SIRA writes BM25 indexes, DF stores, and enriched corpora.
- `sira-kb-ingestor` writes `tickets.arrow`, `ticket_index.faiss`, `enriched_kb.jsonl`, `kb_index.pkl`, and `setup_summary.json`.
- CatalogAgent writes provenance artifacts and runtime state in its own artifact store.

### 4. Prefer the subproject docs over root summaries

The root `AGENTS.md` gives workspace-wide conventions, but it also points you to the local docs for the details that matter when editing code.

## What to check before editing

For any subproject, the safest first-pass sequence is:

1. Read the local `AGENTS.md` or `CLAUDE.md`.
2. Read the subproject `README.md` or spec documents.
3. Inspect the packaging file (`pyproject.toml`) for entrypoints and dependencies.
4. Read the main runtime modules and tests that cover the code you want to change.

## Cross-project dependency notes

Some workspaces feed others:

- `AAFLOW-2605.02162/` and `sira-kb-ingestor/` both produce data products that SIRA consumes.
- `sira-kb-ingestor` explicitly imports both AAFLOW-style ingest code and SIRA enrichment code when building its combined artifacts.

That means changes to an upstream data schema or artifact name should be checked against the consuming project before landing.

## Evidence used for this page

- `/README.md`
- `/AGENTS.md`
- `/sira/AGENTS.md`
- `/sira/CLAUDE.md`
- `/datamaster/CLAUDE.md`
- `/sira-kb-ingestor/README.md`
- `/AAFLOW-2605.02162/README.md`
- `/AAFLOW-2605.02162/AGENTS.md`
