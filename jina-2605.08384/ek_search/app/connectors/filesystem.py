"""FileSystemConnector — scans local directory for text/image/PDF files."""
from __future__ import annotations
from pathlib import Path
from typing import Iterator
import hashlib

from app.models import Document

TEXT_EXTS = {".md", ".txt", ".rst", ".html", ".py", ".json", ".yaml", ".yml", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
PDF_EXTS = {".pdf"}


class FileSystemConnector:

    def __init__(self, path: str | Path, recursive: bool = True):
        self.root = Path(path)
        self.recursive = recursive

    def scan(self) -> Iterator[Document]:
        if not self.root.exists():
            raise FileNotFoundError(f"Path not found: {self.root}")

        pattern = "**/*" if self.recursive else "*"
        for p in sorted(self.root.glob(pattern)):
            if not p.is_file():
                continue
            suffix = p.suffix.lower()
            if suffix in TEXT_EXTS:
                yield self._make_text_doc(p)
            elif suffix in IMAGE_EXTS:
                yield self._make_image_doc(p)
            elif suffix in PDF_EXTS:
                yield self._make_pdf_doc(p)
            # skip unknown types silently

    def _make_text_doc(self, p: Path) -> Document:
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = ""
        return Document(
            id=f"src:filesystem:{p.relative_to(self.root) if self.root in p.parents else p.name}",
            content=content,
            modality="text",
            source_system="filesystem",
            asset_url=str(p.resolve()),
            metadata={"filename": p.name, "extension": p.suffix},
        )

    def _make_image_doc(self, p: Path) -> Document:
        raw = p.read_bytes()
        h = "sha256:" + hashlib.sha256(raw).hexdigest()[:16]
        return Document(
            id=f"src:filesystem:{p.name}",
            content=p,                      # pass Path — backend handles it
            modality="image",
            source_system="filesystem",
            asset_url=str(p.resolve()),
            metadata={"filename": p.name, "extension": p.suffix},
            content_hash=h,
        )

    def _make_pdf_doc(self, p: Path) -> Document:
        raw = p.read_bytes()
        h = "sha256:" + hashlib.sha256(raw).hexdigest()[:16]
        return Document(
            id=f"src:filesystem:{p.name}",
            content=p,
            modality="pdf",
            source_system="filesystem",
            asset_url=str(p.resolve()),
            metadata={"filename": p.name, "extension": p.suffix},
            content_hash=h,
        )
