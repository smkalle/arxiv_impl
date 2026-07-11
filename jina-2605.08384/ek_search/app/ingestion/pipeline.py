"""IngestionPipeline — batched, idempotent, with retry."""
from __future__ import annotations
import logging
import time
from typing import Iterator

from app.models import Document, Chunk, IngestResponse
from app.ingestion.preprocessor import DocumentPreprocessor
from app.vector_store import ChromaVectorStore
from app.backends.base import EmbeddingBackend

logger = logging.getLogger(__name__)


class IngestionPipeline:

    def __init__(
        self,
        backend: EmbeddingBackend,
        store: ChromaVectorStore,
        preprocessor: DocumentPreprocessor | None = None,
        batch_size: int = 32,
        max_retries: int = 3,
    ):
        self.backend = backend
        self.store = store
        self.preprocessor = preprocessor or DocumentPreprocessor()
        self.batch_size = batch_size
        self.max_retries = max_retries

    def ingest_documents(
        self,
        documents: list[Document],
        acl_groups: list[str] | None = None,
    ) -> IngestResponse:
        t0 = time.monotonic()
        ingested = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        # Flatten documents → chunks
        all_chunks: list[Chunk] = []
        for doc in documents:
            try:
                chunks = self.preprocessor.process(doc, acl_groups=acl_groups or ["public"])
                all_chunks.extend(chunks)
            except Exception as e:
                failed += 1
                errors.append(f"{doc.id}: {e}")
                logger.warning("Preprocessing failed for %s: %s", doc.id, e)

        # Idempotency: skip chunks already in store (by content_hash)
        new_chunks: list[Chunk] = []
        for chunk in all_chunks:
            existing = self.store.get_by_hash(chunk.content_hash)
            if existing:
                skipped += 1
            else:
                new_chunks.append(chunk)

        # Batch embed + store
        for i in range(0, len(new_chunks), self.batch_size):
            batch = new_chunks[i:i + self.batch_size]
            for attempt in range(self.max_retries):
                try:
                    inputs = [c.content for c in batch]
                    embeddings = self.backend.embed(inputs)
                    self.store.add_chunks(batch, embeddings)
                    ingested += len(batch)
                    break
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        failed += len(batch)
                        errors.append(f"batch {i}: {e}")
                        logger.error("Batch %d failed after %d retries: %s", i, self.max_retries, e)
                    else:
                        wait = 2 ** attempt
                        logger.warning("Batch %d attempt %d failed, retrying in %ds: %s", i, attempt, wait, e)
                        time.sleep(wait)

        duration_ms = (time.monotonic() - t0) * 1000
        return IngestResponse(
            status="ok",
            ingested=ingested,
            skipped=skipped,
            failed=failed,
            duration_ms=round(duration_ms, 1),
            errors=errors[:10],  # cap error list
        )
