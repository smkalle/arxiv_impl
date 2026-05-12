import pyarrow as pa
import pyarrow.compute as pc

from kb_ingestor.models import IngestConfig
from kb_ingestor.ops.chunk import chunk


def _base_table() -> pa.Table:
    return pa.table(
        {
            "id": ["1", "2", "3"],
            "subject": ["Login", "JP", "AR"],
            "description": [
                "Cannot sign in because session cookie keeps expiring unexpectedly",
                "これは日本語の説明テキストです。十分な文字数があります。",
                "هذا نص عربي لاختبار التعامل مع UTF-8 بشكل صحيح",
            ],
            "status": ["open", "open", "open"],
            "created_at": [None, None, None],
            "tags": [["auth"], ["jp"], ["ar"]],
            "source": ["zendesk", "zendesk", "zendesk"],
        }
    )


def test_chunk_vectorized() -> None:
    table = _base_table()
    out = chunk(table, IngestConfig(max_chunk_chars=20, min_chunk_chars=5))
    assert out.num_rows == 3
    assert "chunk" in out.column_names
    assert "chunk_index" in out.column_names
    lens = pc.utf8_length(out.column("chunk")).to_pylist()
    assert all(l <= 20 for l in lens)
    assert out.column("chunk_index").to_pylist() == [0, 0, 0]


def test_chunk_min_chars_filter() -> None:
    table = pa.table(
        {
            "id": ["1", "2"],
            "subject": ["A", "LongSubject"],
            "description": ["B", "Long description text for retention"],
            "status": ["open", "open"],
            "created_at": [None, None],
            "tags": [["x"], ["y"]],
            "source": ["zendesk", "zendesk"],
        }
    )
    out = chunk(table, IngestConfig(min_chunk_chars=10, max_chunk_chars=50))
    assert out.num_rows == 1
    assert out.column("id").to_pylist() == ["2"]


def test_chunk_utf8_edges() -> None:
    table = pa.table(
        {
            "id": ["1", "2"],
            "subject": ["日本語", "العربية"],
            "description": ["テキストテキストテキスト", "نص عربي طويل للاختبار"],
            "status": ["open", "open"],
            "created_at": [None, None],
            "tags": [["jp"], ["ar"]],
            "source": ["jira", "jira"],
        }
    )
    out = chunk(table, IngestConfig(max_chunk_chars=12, min_chunk_chars=4))
    assert out.num_rows == 2
    chunks = out.column("chunk").to_pylist()
    assert all(isinstance(c, str) for c in chunks)
    assert all(len(c) > 0 for c in chunks)
