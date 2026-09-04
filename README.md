# arxiv_impl

Implementations of arXiv papers. Each paper implementation lives in its own folder as a self-contained subproject with its own deps, test command, and run location.

The root-level `AGENTS.md` is the canonical contributor guide; `openwiki/` holds extended architecture notes. There is no root application, package, or test suite — `cd` into the relevant subproject and follow its local docs.

## Table of contents

| Folder | Paper | Summary | Status |
|---|---|---|---|
| `sira/` | [Meta SIRA (arXiv:2605.06647)](https://arxiv.org/abs/2605.06647) | Training-free support-ticket → KB retrieval via offline LLM enrichment + online sketch expansion + weighted BM25 | Iterations 1–5 code complete (placeholder eval set; real annotation data pending) |
| `AAFLOW-2605.02162/` | [AAFLOW (arXiv:2605.02162)](https://arxiv.org/abs/2605.02162) | Zero-copy Arrow-native ticket ingest pipeline (Zendesk CSV / Jira JSON) → FAISS with async batching; outputs `tickets.arrow`, `index.faiss`, `run_summary.json` | v0.1.0 release-ready |
| `datamaster/` | [DataMaster (arXiv:2605.10906)](https://arxiv.org/abs/2605.10906) | Autonomous e-commerce catalog enrichment agent: UCB-1 tree-scheduled red/black nodes discover external attribute data (GS1, Open Food Facts), merge via conflict-resolution policy, commit only on positive score delta — frozen scorer, full rollback, provenance artifacts, FastAPI + management console UI | v0.1.0 complete; 42 tests pass; smoke test `avg_score_delta > 0` verified |
| `jina-2605.08384/` | [Jina (arXiv:2605.08384)](https://arxiv.org/abs/2605.08384) | Enterprise knowledge search prototype (`ek_search/`, FastAPI); spec + iteration plan + use-case docs | Prototype |
| `sira-kb-ingestor/` | SIRA KB ingestor package | Standalone ingestor producing SIRA's enrichment input; `sira_kb_ingestor/` lib + `scripts/` + `tests/` | v0.1.0 |
| `tkmem-2605.13941/` | TKMEM / TicketMind (arXiv:2605.13941) | TicketMind retrieval prototype spec + dashboard; implementation lives under its nested `sira/` | Spec + partial |
| `evolvemem-2605.13941/` | EvolveMem (arXiv:2605.13941) | EvolvMem runner implementing L1→L2→L3→L4 loops over the SIRA pipeline; FastAPI (`api.py`), loop runner, systemd units, dashboard, dev set + pytest suite | Implementation present; tests defined |
| `rgqm/` | Red Queen Gödel Machine (arXiv:2606.26294) | EpochForge Lite prototype: co-evolving coder + reviewer agents, single epoch boundary at step 30, ε-best-belief promotion, selective erasure; `archive.py` / `search.py` / `agents.py` / `llm.py` / `plot.py` + HumanEval task set + erasure-invariant test; HGM-H baseline = same code with frozen reviewer | Implementation present; erasure-invariant test passing |
| `orchestrator/` | **metaorch** — meta-orchestrator pipeline chaining all 8 subprojects' use cases end-to-end (ingest → KB enrich → SIRA/TicketMind/Jina retrieval → catalog enrich → EvolveMem → RGQM) via minimal contract-bound adapters; FastAPI + Pydantic v2, in-memory fakes, no sibling imports | v0.1.0; 120 tests pass |
| `lfm25-grpo-ifstruct/` | [Fine-tuning a 350M Model for Better Structured Outputs in 100 GRPO Steps](https://huggingface.co/blog/grpo-with-trl-ifstruct) (HF blog, not arXiv) | Hands-on Colab notebook: GRPO-tune `LiquidAI/LFM2.5-350M` for schema-compliant JSON against the [IFStruct](https://github.com/Liquid4All/ifstruct) benchmark. Training half is verbatim from Liquid's official cookbook notebook (Nemotron data, published hyperparameters, 3 rewards); evaluation half calls Liquid's own `validate_response()` rather than re-implementing it. Smoke mode, paired sign test, GGUF/`llama-server` official-eval path, YAML-extension generator appendix | Notebook complete; CPU cells verified against the real 2,000-row test set (training needs a T4) |

See root `AGENTS.md` for the authoritative per-subproject docs map (`AGENTS.md` / `CLAUDE.md` / `*-spec*.md` / `ITERATIONS.md`).

## Usage

Enter any implementation folder and follow its local docs/scripts.

```bash
# Example: run SIRA tests
cd sira
python3 -m pytest tests/
```

## Conventions

- Use `python3`, not `python` (the latter is not on PATH anywhere in this repo).
- No root CI, no root `pyproject.toml`, no root `requirements.txt`, no root test/lint command — each subproject defines its own. Run commands from inside the subproject folder, never from the repo root.
- Generated artifacts (BM25 pickles, `df_store.json`, enriched corpora, FAISS indexes, Arrow files, `archive.json`, `.env`, venvs, `.pytest_cache`) are gitignored — do not commit these. See root `.gitignore` for per-project ignore rules.
- No git submodules; every subproject is a plain top-level directory.