# arxiv_impl

Implementations of arXiv papers. Each paper implementation lives in its own folder.

## Table of contents

| Folder | Paper | Summary | Status |
|---|---|---|---|
| `sira/` | [Meta SIRA (arXiv:2605.06647)](https://arxiv.org/abs/2605.06647) | Training-free support-ticket to KB retrieval via offline LLM enrichment + online sketch expansion + weighted BM25 | Iterations 1-5 code complete (placeholder eval set; real annotation data pending) |
| `AAFLOW-2605.02162/` | [AAFLOW (arXiv:2605.02162)](https://arxiv.org/abs/2605.02162) | Zero-copy Arrow-native support-ticket ingest pipeline (Zendesk CSV / Jira JSON) to FAISS with async batching; outputs `tickets.arrow`, `index.faiss`, and `run_summary.json` | Iterations 0-10 complete; v0.1.0 release-ready with full validator signoff |
| `datamaster/` | [DataMaster (arXiv:2605.10906)](https://arxiv.org/abs/2605.10906) | Autonomous e-commerce catalog enrichment agent: UCB-1 tree-scheduled red/black nodes discover external attribute data (GS1, Open Food Facts), merge via conflict-resolution policy, commit only on positive score delta — frozen scorer, full rollback, provenance artifacts, FastAPI + management console UI | v0.1.0 complete; 42 tests pass; smoke test avg_score_delta > 0 verified |

## Usage

Enter any implementation folder and follow its local docs/scripts.

Example:

```bash
cd sira
python3 -m pytest tests/
```
