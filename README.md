# arxiv_impl

Implementations of arXiv papers. Each paper implementation lives in its own folder.

## Table of contents

| Folder | Paper | Summary | Status |
|---|---|---|---|
| `sira/` | Meta SIRA (arXiv:2605.06647) | Training-free support-ticket to KB retrieval via offline LLM enrichment + online sketch expansion + weighted BM25 | Iterations 1-5 code complete (placeholder eval set; real annotation data pending) |

## Usage

Enter any implementation folder and follow its local docs/scripts.

Example:

```bash
cd sira
python3 -m pytest tests/
```
