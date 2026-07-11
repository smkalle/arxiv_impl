# UC-1 · Enterprise Knowledge Search — Technical Specification
**Version:** 1.0 · **Status:** Approved for implementation  
**Model:** `jina-embeddings-v5-omni-small` (prod) · `all-MiniLM-L6-v2` (dev/test stub)  
**Stack:** Python 3.12 · FastAPI · Chroma · SentenceTransformers · Jina API (optional)

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     SOURCE CONNECTORS                           │
│  FileSystemConnector · ConfluenceConnector · NotionConnector    │
│  FigmaConnector · LoomConnector  (all implement BaseConnector)  │
└──────────────────────────┬──────────────────────────────────────┘
                           │  List[Document]
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    INGESTION LAYER                              │
│  DocumentPreprocessor   →  chunk / resize / audio-extract       │
│  IngestionPipeline      →  batch · idempotent · retry           │
│  IngestionQueue         →  in-proc (v1) · Redis (v3)            │
└──────────────────────────┬──────────────────────────────────────┘
                           │  List[Chunk]  (id, content, metadata)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              EMBEDDING BACKEND  (config-switchable)             │
│  EmbeddingBackend (ABC)                                         │
│  ├── LocalBackend   →  SentenceTransformer  (EMBEDDING_BACKEND=local) │
│  ├── JinaAPIBackend →  api.jina.ai/v1/embeddings  (=jina_api)  │
│  └── StubBackend    →  random vectors  (=stub, tests only)      │
└──────────────────────────┬──────────────────────────────────────┘
                           │  np.ndarray[n, EMBED_DIM]
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     VECTOR STORE                                │
│  ChromaVectorStore  →  PersistentClient + HNSW cosine index     │
│  Collection: multimodal-knowledge                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  RETRIEVAL API  (FastAPI)                       │
│  POST /ingest      →  trigger ingestion from connector          │
│  POST /search      →  query + filter → ranked results           │
│  GET  /health      →  backend + index stats                     │
│  GET  /stats       →  document counts by modality/source        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│             DASHBOARD  (static HTML + vanilla JS)               │
│  Ingest panel · Search panel · Eval panel · Stats panel         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Model

### 2.1 Document (connector output)
```python
@dataclass
class Document:
    id: str                   # "src:{system}:{path_or_id}"
    content: Any              # str | PIL.Image | Path(audio) | Path(video)
    modality: str             # "text" | "image" | "audio" | "video" | "pdf"
    source_system: str        # "filesystem" | "confluence" | "notion" | "figma" | "loom"
    asset_url: str            # original URL or file path
    metadata: dict            # arbitrary source metadata
    created_at: datetime
    content_hash: str         # SHA256 of raw content — idempotency key
```

### 2.2 Chunk (preprocessor output)
```python
@dataclass
class Chunk:
    id: str                   # "{doc_id}:chunk_{n}"
    document_id: str
    content: Any              # same types as Document.content
    modality: str
    source_system: str
    asset_url: str
    chunk_index: int
    token_count: int          # 0 for non-text
    acl_groups: list[str]     # ["public"] default
    metadata: dict
    content_hash: str
```

### 2.3 Chroma record schema
```python
collection.add(
    ids=["src:filesystem:readme.md:chunk_0"],
    embeddings=[[...float32 × EMBED_DIM...]],
    documents=["raw text or asset ref string"],
    metadatas=[{
        "modality":          "text",
        "source_system":     "filesystem",
        "asset_url":         "/data/samples/readme.md",
        "acl_groups":        '["public"]',   # JSON-encoded (Chroma flat values only)
        "chunk_index":       0,
        "token_count":       342,
        "task_adapter":      "retrieval",
        "embed_dim":         384,            # actual stored dim
        "content_hash":      "sha256:abc...",
        "created_at":        "2026-05-16T10:00:00Z",
    }]
)
```

### 2.4 Search request / response
```python
# Request
class SearchRequest(BaseModel):
    query_text: str | None = None
    query_image_b64: str | None = None   # base64 PNG/JPEG
    n_results: int = 10
    modality_filter: list[str] = []      # [] = all modalities
    source_filter: list[str] = []        # [] = all sources
    min_score: float = 0.0

# Response
class SearchResult(BaseModel):
    id: str
    score: float
    modality: str
    source_system: str
    snippet: str                         # first 200 chars of document
    asset_url: str
    chunk_index: int
    metadata: dict

class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query_latency_ms: float
    backend_used: str
    embed_dim: int
```

---

## 3. Embedding Backend Interface

```python
class EmbeddingBackend(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def embed_dim(self) -> int: ...

    @abstractmethod
    def embed(self, inputs: list[Any]) -> np.ndarray:
        """Embed a mixed list of text str | PIL.Image | Path objects.
        Returns float32 ndarray shape (n, embed_dim), L2-normalized."""
        ...

    def embed_query(self, query: str) -> np.ndarray:
        """Single text query embedding. Default: calls embed([query])."""
        return self.embed([query])[0]
```

---

## 4. Configuration

All config via environment variables with `.env` file support (python-dotenv).

```bash
# Backend selection
EMBEDDING_BACKEND=stub          # stub | local | jina_api

# Local backend
LOCAL_MODEL_ID=all-MiniLM-L6-v2          # dev default (fast, small)
# LOCAL_MODEL_ID=jinaai/jina-embeddings-v5-omni-small  # production

# Jina API backend
JINA_API_KEY=jina_xxxx
JINA_MODEL=jina-embeddings-v5-omni-small
JINA_TASK=retrieval.passage
JINA_DIMENSIONS=512

# Embedding tuning
EMBED_DIM=384                   # override (Matryoshka truncation)
TASK_ADAPTER=retrieval

# Chroma
CHROMA_PATH=./data/chroma
CHROMA_COLLECTION=multimodal-knowledge

# Ingestion
INGEST_BATCH_SIZE=32
INGEST_MAX_RETRIES=3

# API
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
```

---

## 5. API Contract

### POST /ingest
```json
// Request
{ "source": "filesystem", "path": "./data/samples", "acl_groups": ["public"] }

// Response
{ "status": "ok", "ingested": 12, "skipped": 3, "failed": 0, "duration_ms": 1420 }
```

### POST /search
```json
// Request
{ "query_text": "onboarding flow", "n_results": 5, "modality_filter": ["text"] }

// Response
{
  "results": [
    {
      "id": "src:filesystem:onboarding.md:chunk_0",
      "score": 0.912,
      "modality": "text",
      "source_system": "filesystem",
      "snippet": "## Onboarding Flow\nStep 1: Create your account...",
      "asset_url": "./data/samples/onboarding.md",
      "chunk_index": 0,
      "metadata": {}
    }
  ],
  "total": 1,
  "query_latency_ms": 23.4,
  "backend_used": "local",
  "embed_dim": 384
}
```

### GET /health
```json
{
  "status": "ok",
  "backend": "local",
  "model_id": "all-MiniLM-L6-v2",
  "embed_dim": 384,
  "collection": "multimodal-knowledge",
  "document_count": 47,
  "chroma_path": "./data/chroma"
}
```

### GET /stats
```json
{
  "total_chunks": 47,
  "by_modality": { "text": 40, "image": 7 },
  "by_source": { "filesystem": 47 },
  "index_size_mb": 0.8
}
```

---

## 6. Eval Framework

Golden pairs stored in `data/golden/golden_pairs.json`:
```json
[
  {
    "id": "q001",
    "query_text": "onboarding flow steps",
    "expected_doc_ids": ["src:filesystem:onboarding.md:chunk_0"],
    "modality": "text"
  }
]
```

Metrics computed:
- **Precision@k** (k=1,3,5) — fraction of top-k results in expected set
- **Recall@k** — fraction of expected docs found in top-k
- **MRR** — mean reciprocal rank of first relevant result
- **Latency p50/p95** — across all golden queries

---

## 7. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Query p95 (stub backend) | < 50ms |
| Query p95 (local, 384-dim) | < 200ms |
| Ingestion throughput | ≥ 20 docs/min |
| Index capacity (v1) | ≥ 10K chunks |
| Test coverage | ≥ 85% line coverage |
| All tests pass | `pytest -q` green |

---

## 8. Security Notes (v1 scope)

- ACL groups stored as JSON-encoded string in Chroma metadata
- Pre-filter on `acl_groups` applied before returning results
- No authentication on API in v1 (internal tooling; add Bearer token in v2)
- No PII masking in v1 (filesystem samples only; required before Jina API with prod data)
