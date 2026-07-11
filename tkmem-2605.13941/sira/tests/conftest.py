from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from src.retrieve import _set_index


@pytest.fixture(autouse=True)
def reset_retrieve_index():
    _set_index(None)
    yield
    _set_index(None)


@pytest.fixture
def tiny_corpus(tmp_path: Path) -> Path:
    corpus_path = tmp_path / "kb.jsonl"
    corpus_path.write_text(
        "\n".join(
            [
                '{"id":"KB-A","title":"Login crash","body":"App crashes after login because the session token is corrupted."}',
                '{"id":"KB-B","title":"Billing renewal","body":"Subscription renewal fails when the saved payment card is rejected."}',
                '{"id":"KB-C","title":"Password email","body":"Password reset email may be delayed or filtered as spam."}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return corpus_path
