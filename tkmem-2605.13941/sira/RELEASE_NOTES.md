# TicketMind/TKMEM Local Release Notes

This release is framed around arXiv `2605.13941` and EvolveMem/TKMEM. Legacy SIRA wording has been replaced in user-facing commands and docs; `--sira` remains only as a backward-compatible CLI alias.

## Completed Iterations

- Iteration 0-1: project skeleton, BM25 indexing, DF store, plain CLI retrieval.
- Iteration 2: offline enrichment with Ollama-compatible backend and deterministic fallback.
- Iteration 3: online sketch generation, DF validation, hallucination trace.
- Iteration 4: weighted TKMEM/EvolveMem-style retrieval and CLI trace output.
- Iteration 5: annotated test set and evaluation harness.
- Iteration 6: FastAPI retrieval API with health, query, session, and evolution endpoints.
- Iteration 7: FastAPI dashboard for query inspection, KB browsing, evolution monitor, and system health.
- Iteration 8: local compatibility evolution/session implementation with dependency status reporting.
- Iteration 9: operations status script, systemd service templates, and human validation guide.

## Compatibility Notes

SimpleMem and LanceDB are optional in this local release. When not installed, evolution runs in deterministic compatibility mode and reports that status in `data/evolution_state.json`, `/health`, and the dashboard System page.

Generated artifacts are ignored by git and reproducible from the commands in `docs/HUMAN_VALIDATION.md`.
