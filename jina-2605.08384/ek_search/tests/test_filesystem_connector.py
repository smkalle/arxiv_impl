"""Iteration 2 — filesystem connector tests."""
import pytest
from pathlib import Path
from app.connectors.filesystem import FileSystemConnector


SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"


def test_scan_finds_markdown(tmp_path):
    (tmp_path / "doc.md").write_text("# Hello\nworld")
    (tmp_path / "notes.txt").write_text("plain text")
    conn = FileSystemConnector(tmp_path)
    docs = list(conn.scan())
    assert len(docs) == 2
    modalities = {d.modality for d in docs}
    assert "text" in modalities


def test_scan_finds_images(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    img.save(tmp_path / "test.png")
    conn = FileSystemConnector(tmp_path)
    docs = list(conn.scan())
    image_docs = [d for d in docs if d.modality == "image"]
    assert len(image_docs) == 1
    assert image_docs[0].source_system == "filesystem"


def test_scan_source_system(tmp_path):
    (tmp_path / "file.md").write_text("content")
    conn = FileSystemConnector(tmp_path)
    docs = list(conn.scan())
    assert all(d.source_system == "filesystem" for d in docs)


def test_scan_document_ids(tmp_path):
    (tmp_path / "readme.md").write_text("content")
    conn = FileSystemConnector(tmp_path)
    docs = list(conn.scan())
    assert all(d.id.startswith("src:filesystem:") for d in docs)


def test_scan_content_hash_set(tmp_path):
    (tmp_path / "doc.md").write_text("hello world")
    conn = FileSystemConnector(tmp_path)
    docs = list(conn.scan())
    assert all(d.content_hash.startswith("sha256:") for d in docs)


def test_scan_missing_path():
    conn = FileSystemConnector("/nonexistent/path/abc")
    with pytest.raises(FileNotFoundError):
        list(conn.scan())


def test_scan_recursive(tmp_path):
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (tmp_path / "top.md").write_text("top level")
    (subdir / "nested.md").write_text("nested")
    conn = FileSystemConnector(tmp_path, recursive=True)
    docs = list(conn.scan())
    assert len(docs) == 2


def test_scan_non_recursive(tmp_path):
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (tmp_path / "top.md").write_text("top level")
    (subdir / "nested.md").write_text("nested")
    conn = FileSystemConnector(tmp_path, recursive=False)
    docs = list(conn.scan())
    assert len(docs) == 1


def test_scan_real_samples():
    if not SAMPLES_DIR.exists():
        pytest.skip("data/samples not found")
    conn = FileSystemConnector(SAMPLES_DIR)
    docs = list(conn.scan())
    assert len(docs) >= 6
    text_docs = [d for d in docs if d.modality == "text"]
    image_docs = [d for d in docs if d.modality == "image"]
    assert len(text_docs) >= 5
    assert len(image_docs) >= 1
