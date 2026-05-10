from pathlib import Path
import pytest

CORPUS_PATH = Path(__file__).parent.parent / "data" / "kb_corpus.jsonl"
INDEX_PATH = Path(__file__).parent.parent / "data" / "bm25_index.pkl"
