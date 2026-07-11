# OpenWiki quickstart

This repository is a multi-paper workspace for arXiv paper implementations. There is no single root application; each top-level subdirectory is an independent project with its own dependencies, tests, runtime commands, and documentation. Start here, then jump into the relevant domain page for the project you want to change.

## What lives here

- `sira/` — Meta SIRA retrieval pipeline: offline KB enrichment, online sketch expansion, weighted BM25 retrieval, and a FastAPI UI/API surface.
- `AAFLOW-2605.02162/` — Arrow-native ticket ingest pipeline into FAISS, intended to feed downstream retrieval systems.
- `datamaster/` — CatalogAgent/DataMaster-style autonomous e-commerce enrichment agent with red/black tree scheduling, external sources, and provenance-first commits.
- `sira-kb-ingestor/` — Combined ingest + enrichment + retrieval package that bridges AAFLOW-style ticket ingestion with SIRA KB artifacts.
- `jina-2605.08384/` — Enterprise knowledge search prototype, documented locally.
- `tkmem-2605.13941/` — TicketMind / EvolveMem prototype, mostly spec-led.
- `rgqm/` — Red Queen Gödel Machine / EpochForge Lite spec workspace.

## Canonical repo rules

- Run commands from inside the subproject you are modifying, not from the repo root.
- Use `python3`; `python` is not guaranteed to exist.
- Do not assume cross-project compatibility without checking the consuming project's spec or docs.
- Generated artifacts are generally not committed; each subproject documents its own output contract.

## Start here by task

- Need the repo-wide structure and conventions? Read [architecture overview](architecture/overview.md).
- Need to work on SIRA retrieval or enrichment? Read [SIRA](domains/sira.md).
- Need to work on catalog enrichment / DataMaster? Read [CatalogAgent](domains/catalog-agent.md).
- Need to work on ticket ingestion + combined setup flow? Read [SIRA KB ingestor](domains/sira-kb-ingestor.md).

## Useful source references

- Root summary: `/README.md`
- Workspace guidance: `/AGENTS.md`
- SIRA local guidance: `/sira/AGENTS.md`, `/sira/CLAUDE.md`
- CatalogAgent local guidance: `/datamaster/CLAUDE.md`
- SIRA KB ingestor docs: `/sira-kb-ingestor/README.md`

## Suggested reading order for future agents

1. Read this page.
2. Open the domain page for the area you plan to change.
3. Read that subproject's own `AGENTS.md` / `CLAUDE.md` before editing code.
4. Check the relevant `pyproject.toml`, `README.md`, and core source files before making changes.

## Sections

- [Architecture overview](architecture/overview.md)
- [SIRA](domains/sira.md)
- [CatalogAgent](domains/catalog-agent.md)
- [SIRA KB ingestor](domains/sira-kb-ingestor.md)
