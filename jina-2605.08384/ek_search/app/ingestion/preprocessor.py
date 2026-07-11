"""DocumentPreprocessor — converts Documents into embeddable Chunks."""
from __future__ import annotations
from pathlib import Path
from app.models import Document, Chunk


def _simple_token_count(text: str) -> int:
    """Approximate token count (whitespace split)."""
    return len(text.split())


def chunk_text(
    text: str,
    doc_id: str,
    chunk_size: int = 256,       # tokens (words approx)
    overlap: int = 32,
) -> list[tuple[str, int, int]]:
    """Split text into overlapping chunks.
    Returns list of (chunk_text, chunk_index, token_count).
    Uses word-level splitting for simplicity and portability.
    """
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    idx = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        chunk_text_str = " ".join(chunk_words)
        chunks.append((chunk_text_str, idx, len(chunk_words)))
        if end >= len(words):
            break
        start += chunk_size - overlap
        idx += 1

    return chunks


class DocumentPreprocessor:

    def __init__(
        self,
        text_chunk_size: int = 256,
        text_overlap: int = 32,
        image_max_px: int = 1024,
    ):
        self.text_chunk_size = text_chunk_size
        self.text_overlap = text_overlap
        self.image_max_px = image_max_px

    def process(self, doc: Document, acl_groups: list[str] | None = None) -> list[Chunk]:
        acl = acl_groups or ["public"]
        if doc.modality == "text":
            return self._process_text(doc, acl)
        elif doc.modality == "image":
            return self._process_image(doc, acl)
        elif doc.modality == "pdf":
            return self._process_pdf(doc, acl)
        elif doc.modality in ("audio", "video"):
            return self._process_av(doc, acl)
        else:
            # Unknown — single chunk passthrough
            return [Chunk(
                id=f"{doc.id}:chunk_0",
                document_id=doc.id,
                content=doc.content,
                modality=doc.modality,
                source_system=doc.source_system,
                asset_url=doc.asset_url,
                chunk_index=0,
                token_count=0,
                acl_groups=acl,
                metadata=doc.metadata,
                content_hash=doc.content_hash,
            )]

    def _process_text(self, doc: Document, acl: list[str]) -> list[Chunk]:
        text = doc.content if isinstance(doc.content, str) else str(doc.content)
        raw_chunks = chunk_text(text, doc.id, self.text_chunk_size, self.text_overlap)
        chunks = []
        for chunk_str, idx, tcount in raw_chunks:
            chunks.append(Chunk(
                id=f"{doc.id}:chunk_{idx}",
                document_id=doc.id,
                content=chunk_str,
                modality="text",
                source_system=doc.source_system,
                asset_url=doc.asset_url,
                chunk_index=idx,
                token_count=tcount,
                acl_groups=acl,
                metadata=doc.metadata,
            ))
        return chunks

    def _process_image(self, doc: Document, acl: list[str]) -> list[Chunk]:
        # Store the image path/object; embedding backend handles it
        content = doc.content
        if isinstance(content, str):
            content = Path(content)

        return [Chunk(
            id=f"{doc.id}:chunk_0",
            document_id=doc.id,
            content=content,
            modality="image",
            source_system=doc.source_system,
            asset_url=doc.asset_url,
            chunk_index=0,
            token_count=0,
            acl_groups=acl,
            metadata=doc.metadata,
            content_hash=doc.content_hash,
        )]

    def _process_pdf(self, doc: Document, acl: list[str]) -> list[Chunk]:
        # v1: extract text from PDF using basic approach, then chunk
        content = doc.content
        text = ""
        if isinstance(content, (str, Path)):
            path = Path(content)
            if path.exists():
                try:
                    import pypdf
                    reader = pypdf.PdfReader(str(path))
                    text = "\n\n".join(
                        page.extract_text() or "" for page in reader.pages
                    ).strip()
                except Exception:
                    text = f"[PDF: {path.name}]"
            else:
                text = f"[PDF: {path}]"
        elif isinstance(content, str):
            text = content

        if not text:
            text = f"[PDF: {doc.asset_url}]"

        text_doc = Document(
            id=doc.id,
            content=text,
            modality="text",
            source_system=doc.source_system,
            asset_url=doc.asset_url,
            metadata=doc.metadata,
        )
        chunks = self._process_text(text_doc, acl)
        for c in chunks:
            c.modality = "pdf"
        return chunks

    def _process_av(self, doc: Document, acl: list[str]) -> list[Chunk]:
        return [Chunk(
            id=f"{doc.id}:chunk_0",
            document_id=doc.id,
            content=doc.content,
            modality=doc.modality,
            source_system=doc.source_system,
            asset_url=doc.asset_url,
            chunk_index=0,
            token_count=0,
            acl_groups=acl,
            metadata=doc.metadata,
            content_hash=doc.content_hash,
        )]
