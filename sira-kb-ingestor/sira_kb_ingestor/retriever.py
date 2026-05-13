from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sira_kb_ingestor.errors import RetrievalError
from sira_kb_ingestor.orchestration import _ensure_import_paths


class Retriever:
    """Runtime wrapper around SIRA's BM25 retrieval artifacts."""

    def __init__(self, artifact_dir: Path | str = Path("./sira-artifacts")) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.index_path = self.artifact_dir / "kb_index.pkl"
        self._loaded = False
        self._load_error: str | None = None
        self._sira_retrieve_module: Any | None = None
        self._try_load()

    def _import_sira_retrieve(self) -> Any:
        if self._sira_retrieve_module is None:
            _ensure_import_paths()
            import src.retrieve as retrieve_module

            self._sira_retrieve_module = retrieve_module
        return self._sira_retrieve_module

    def _try_load(self) -> bool:
        try:
            self.load()
            return True
        except RetrievalError as exc:
            self._load_error = str(exc)
            return False

    def load(self) -> None:
        if not self.index_path.exists():
            self._loaded = False
            raise RetrievalError(f"KB index not found at {self.index_path}. Run setup first.")

        try:
            retrieve_module = self._import_sira_retrieve()
            retrieve_module.load_index(self.index_path)
        except Exception as exc:
            self._loaded = False
            raise RetrievalError(f"Failed to load KB index at {self.index_path}: {exc}") from exc

        self._loaded = True
        self._load_error = None

    def health(self) -> dict[str, Any]:
        corpus_size = 0
        if self._loaded:
            try:
                retrieve_module = self._import_sira_retrieve()
                index = getattr(retrieve_module, "_index", None)
                corpus_size = len(getattr(index, "articles", [])) if index is not None else 0
            except Exception:
                corpus_size = 0

        return {
            "bm25_index_loaded": self._loaded,
            "corpus_size": corpus_size,
            "index_path": str(self.index_path),
            "index_built_at": self._index_built_at(),
            "load_error": self._load_error,
        }

    def retrieve(
        self,
        ticket_text: str,
        top_k: int = 5,
        tau: float = 0.01,
        weight: float = 1.5,
    ) -> dict[str, Any]:
        if not self._loaded:
            self.load()

        try:
            retrieve_module = self._import_sira_retrieve()
            raw = retrieve_module.sira_retrieve(ticket_text, top_k=top_k, tau=tau, w=weight)
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError(f"Retrieval failed: {exc}") from exc

        return self._map_response(raw)

    def _index_built_at(self) -> str | None:
        if not self.index_path.exists():
            return None
        ts = datetime.fromtimestamp(self.index_path.stat().st_mtime, tz=timezone.utc)
        return ts.isoformat()

    @staticmethod
    def _map_response(raw: dict[str, Any]) -> dict[str, Any]:
        articles = []
        for item in raw.get("results", []):
            articles.append({
                "id": item.get("article_id") or item.get("id"),
                "title": item.get("title", ""),
                "body": item.get("body") or item.get("snippet", ""),
                "score": item.get("score", 0.0),
                "matched_terms": item.get("matched_original_terms", item.get("matched_terms", [])),
                "matched_enriched_terms": item.get("matched_enriched_terms", []),
            })

        return {
            "kb_articles": articles,
            "audit": {
                "sketch_terms_generated": raw.get("sketch_terms_generated", []),
                "sketch_terms_validated": raw.get("sketch_terms_validated", []),
                "sketch_terms_rejected": raw.get("sketch_terms_rejected", []),
                "fallback_used": bool(raw.get("fallback_used", False)),
                "latency_ms": int(raw.get("latency_ms", 0)),
                "hallucination_rate": raw.get("hallucination_rate", 0.0),
            },
        }
