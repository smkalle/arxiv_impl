"""ChromaVectorStore — wraps chromadb PersistentClient."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import json
import numpy as np
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.models import Chunk, SearchResult


class ChromaVectorStore:

    def __init__(self, path: str = "./data/chroma", collection_name: str = "multimodal-knowledge"):
        Path(path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ── write ──

    def add_chunks(self, chunks: list[Chunk], embeddings: np.ndarray) -> int:
        """Add chunks with pre-computed embeddings. Returns number added."""
        if not chunks:
            return 0

        ids = [c.id for c in chunks]
        docs = [c.text_for_chroma() for c in chunks]
        metas = [c.metadata_for_chroma() for c in chunks]
        embs = embeddings.tolist()

        # Upsert — overwrite if id already exists
        self._collection.upsert(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
        return len(chunks)

    def delete_by_document(self, document_id: str) -> int:
        """Delete all chunks belonging to a document."""
        results = self._collection.get(where={"document_id": document_id})
        ids = results.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def clear(self) -> None:
        """Delete all documents in the collection."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ── read ──

    def query(
        self,
        query_embedding: np.ndarray,
        n_results: int = 10,
        modality_filter: list[str] | None = None,
        source_filter: list[str] | None = None,
        acl_groups: list[str] | None = None,
    ) -> list[SearchResult]:
        where: dict = {}

        conditions = []
        if modality_filter:
            conditions.append({"modality": {"$in": modality_filter}})
        if source_filter:
            conditions.append({"source_system": {"$in": source_filter}})

        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding.tolist()],
            "n_results": min(n_results, max(1, self.count())),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)

        results = []
        for i, doc_id in enumerate(raw["ids"][0]):
            dist = raw["distances"][0][i]
            # Chroma cosine distance: 0 = identical, 2 = opposite
            score = float(1.0 - dist / 2.0)
            meta = raw["metadatas"][0][i] or {}
            doc_text = raw["documents"][0][i] or ""

            results.append(SearchResult(
                id=doc_id,
                score=round(score, 4),
                modality=meta.get("modality", "text"),
                source_system=meta.get("source_system", ""),
                snippet=doc_text[:300],
                asset_url=meta.get("asset_url", ""),
                chunk_index=int(meta.get("chunk_index", 0)),
                metadata={k: v for k, v in meta.items()
                          if k not in ("modality", "source_system", "asset_url", "chunk_index")},
            ))

        return results

    def get_by_hash(self, content_hash: str) -> list[str]:
        """Return chunk ids with a given content_hash (for idempotency)."""
        results = self._collection.get(where={"content_hash": content_hash})
        return results.get("ids", [])

    def count(self) -> int:
        return self._collection.count()

    def stats(self) -> dict:
        """Return counts by modality and source."""
        total = self.count()
        if total == 0:
            return {"total_chunks": 0, "by_modality": {}, "by_source": {}}

        all_meta = self._collection.get(include=["metadatas"])["metadatas"] or []
        by_modality: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for m in all_meta:
            if m:
                mod = m.get("modality", "unknown")
                src = m.get("source_system", "unknown")
                by_modality[mod] = by_modality.get(mod, 0) + 1
                by_source[src] = by_source.get(src, 0) + 1

        return {
            "total_chunks": total,
            "by_modality": by_modality,
            "by_source": by_source,
        }

    def documents(self, limit: int = 200) -> list[dict]:
        """Return indexed corpus grouped by source document."""
        total = self.count()
        if total == 0:
            return []

        raw = self._collection.get(
            include=["documents", "metadatas"],
            limit=min(limit, total),
        )
        ids = raw.get("ids", [])
        docs = raw.get("documents", []) or []
        metas = raw.get("metadatas", []) or []

        grouped: dict[str, dict] = {}
        for chunk_id, text, meta in zip(ids, docs, metas):
            meta = meta or {}
            document_id = meta.get("document_id") or chunk_id.rsplit(":chunk_", 1)[0]
            item = grouped.setdefault(document_id, {
                "document_id": document_id,
                "asset_url": meta.get("asset_url", ""),
                "source_system": meta.get("source_system", ""),
                "modality": meta.get("modality", "text"),
                "acl_groups": meta.get("acl_groups", "[]"),
                "chunk_count": 0,
                "token_count": 0,
                "chunks": [],
                "snippet": "",
            })
            item["chunk_count"] += 1
            item["token_count"] += int(meta.get("token_count", 0) or 0)
            item["chunks"].append({
                "id": chunk_id,
                "chunk_index": int(meta.get("chunk_index", 0) or 0),
                "token_count": int(meta.get("token_count", 0) or 0),
                "snippet": (text or "")[:220],
            })
            if not item["snippet"] and text:
                item["snippet"] = text[:220]

        return sorted(grouped.values(), key=lambda d: d["asset_url"] or d["document_id"])
