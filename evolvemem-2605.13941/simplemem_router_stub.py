"""
SimpleMem router stub — implements the SimpleMem API surface without requiring
the aiming-lab/SimpleMem clone. Uses:
  - BM25 (rank_bm25) for keyword view
  - Numpy TF-IDF cosine similarity for semantic view (no sentence-transformers)
  - Inverted tag index for symbolic view

This is both a test double and a fallback for environments where SimpleMem
cannot be installed.
"""
from __future__ import annotations

import math
import pickle
import re
from pathlib import Path
from typing import Any

import numpy as np

try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class _TfidfIndex:
    """Minimal numpy TF-IDF cosine similarity index (no external deps beyond numpy)."""

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}
        self._idf: np.ndarray | None = None
        self._matrix: np.ndarray | None = None  # (n_docs, vocab_size), unit-normed

    def fit(self, corpus: list[list[str]]) -> None:
        # Build vocabulary
        all_tokens: set[str] = set()
        for doc in corpus:
            all_tokens.update(doc)
        self._vocab = {t: i for i, t in enumerate(sorted(all_tokens))}
        V = len(self._vocab)
        N = len(corpus)

        # TF matrix
        tf = np.zeros((N, V), dtype=np.float32)
        for d, doc in enumerate(corpus):
            for tok in doc:
                if tok in self._vocab:
                    tf[d, self._vocab[tok]] += 1
            row_sum = tf[d].sum()
            if row_sum > 0:
                tf[d] /= row_sum

        # IDF
        df = (tf > 0).sum(axis=0).astype(np.float32)
        self._idf = np.log((N + 1) / (df + 1)).astype(np.float32)

        # TF-IDF, unit-normalise
        tfidf = tf * self._idf
        norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = (tfidf / norms).astype(np.float32)

    def query(self, tokens: list[str], top_k: int) -> list[tuple[int, float]]:
        if self._matrix is None or len(self._vocab) == 0:
            return []
        V = len(self._vocab)
        qvec = np.zeros(V, dtype=np.float32)
        for tok in tokens:
            if tok in self._vocab:
                qvec[self._vocab[tok]] += 1
        qvec *= self._idf
        norm = float(np.linalg.norm(qvec))
        if norm == 0:
            return []
        qvec /= norm
        scores = self._matrix @ qvec
        indices = np.argsort(scores)[::-1][:top_k]
        return [(int(i), float(scores[i])) for i in indices if scores[i] > 0]


class StubSimpleMemRouter:
    """
    Drop-in stub implementing:
        router = StubSimpleMemRouter().create(mode="text")
        router.add_dialogue(user=..., assistant=..., metadata=...)
        router.finalize()
        results = router.ask(query=..., config=config)
    """

    def __init__(self, lancedb_uri: str | None = None) -> None:
        self._lancedb_uri = lancedb_uri
        self._corpus: list[dict[str, Any]] = []   # raw entries
        self._bm25: Any = None
        self._tfidf = _TfidfIndex()
        self._tag_index: dict[str, list[int]] = {}
        self._finalized = False

    # ── Public API ──────────────────────────────────────────────────────────

    def create(self, mode: str = "text") -> "StubSimpleMemRouter":
        """Reset state and return self (matches real SimpleMem API)."""
        self._corpus = []
        self._bm25 = None
        self._tfidf = _TfidfIndex()
        self._tag_index = {}
        self._finalized = False
        return self

    def add_dialogue(
        self,
        user: str,
        assistant: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a KB article as a dialogue pair."""
        if metadata is None:
            metadata = {}
        self._corpus.append({
            "user": user,
            "assistant": assistant,
            "metadata": metadata,
            "index": len(self._corpus),
        })

    def finalize(self) -> None:
        """Build all three indexes from accumulated corpus."""
        if not self._corpus:
            self._finalized = True
            return

        texts = [f"{e['user']} {e['assistant']}" for e in self._corpus]
        token_lists = [_tokenize(t) for t in texts]

        # BM25
        if _HAS_BM25:
            self._bm25 = BM25Okapi(token_lists)

        # TF-IDF semantic
        self._tfidf.fit(token_lists)

        # Tag/symbolic index
        self._tag_index = {}
        for idx, entry in enumerate(self._corpus):
            tags = entry["metadata"].get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            for tag in tags:
                self._tag_index.setdefault(tag.lower(), []).append(idx)
            # also index product_area as a tag
            pa = entry["metadata"].get("product_area", "")
            if pa:
                self._tag_index.setdefault(pa.lower(), []).append(idx)

        # Optionally persist (mimics LanceDB write)
        if self._lancedb_uri:
            pkl_path = Path(self._lancedb_uri + ".stub.pkl")
            pkl_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pkl_path, "wb") as f:
                pickle.dump({"corpus": self._corpus, "tag_index": self._tag_index}, f)

        self._finalized = True

    def ask(self, query: str, config: Any = None) -> list[dict[str, Any]]:
        """
        Query the three views and blend scores.
        config is expected to be a RetrievalConfig with:
          .top_k, .bm25_weight, .semantic_weight, .symbolic_weight
        """
        if not self._finalized:
            self.finalize()

        top_k = 5
        bm25_w = 1.0
        sem_w = 0.5
        sym_w = 0.2

        if config is not None:
            top_k = getattr(config, "top_k", top_k)
            bm25_w = getattr(config, "bm25_weight", bm25_w)
            sem_w = getattr(config, "semantic_weight", sem_w)
            sym_w = getattr(config, "symbolic_weight", sym_w)

        if not self._corpus:
            return []

        n = len(self._corpus)
        scores = np.zeros(n, dtype=np.float64)
        qtokens = _tokenize(query)

        # BM25 keyword view
        if _HAS_BM25 and self._bm25 is not None:
            bm25_scores = np.array(self._bm25.get_scores(qtokens), dtype=np.float64)
            mx = bm25_scores.max()
            if mx > 0:
                bm25_scores /= mx
            scores += bm25_w * bm25_scores

        # Semantic view (TF-IDF cosine)
        sem_hits = self._tfidf.query(qtokens, top_k=n)
        for idx, s in sem_hits:
            scores[idx] += sem_w * s

        # Symbolic / tag view
        for tok in qtokens:
            for idx in self._tag_index.get(tok, []):
                scores[idx] += sym_w * 0.3  # fixed bonus per tag hit

        # Check for query_expansion / entity_swap in config extras
        if config is not None:
            extras = getattr(config, "_extras", {})
            if extras.get("entity_swap"):
                domain = extras.get("entity_swap_domain", "")
                expanded = _entity_expand(qtokens, domain)
                if expanded != qtokens and _HAS_BM25 and self._bm25 is not None:
                    exp_scores = np.array(self._bm25.get_scores(expanded), dtype=np.float64)
                    mx = exp_scores.max()
                    if mx > 0:
                        exp_scores /= mx
                    scores += bm25_w * 0.5 * exp_scores

        # Sort and return top_k
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for i in top_indices:
            entry = self._corpus[i]
            results.append({
                "article_id": entry["metadata"].get("article_id", f"doc_{i}"),
                "title": entry["metadata"].get("title", ""),
                "score": float(scores[i]),
                "snippet": entry["assistant"][:200],
                "product_area": entry["metadata"].get("product_area", ""),
                "view_scores": {
                    "combined": float(scores[i]),
                },
            })
        return results

    # ── Persistence helpers ──────────────────────────────────────────────────

    @classmethod
    def load(cls, lancedb_uri: str) -> "StubSimpleMemRouter":
        pkl_path = Path(lancedb_uri + ".stub.pkl")
        if not pkl_path.exists():
            return cls(lancedb_uri=lancedb_uri)
        with open(pkl_path, "rb") as f:
            state = pickle.load(f)
        router = cls(lancedb_uri=lancedb_uri)
        for entry in state["corpus"]:
            router.add_dialogue(
                user=entry["user"],
                assistant=entry["assistant"],
                metadata=entry["metadata"],
            )
        router.finalize()
        return router


# ── Domain entity expansion (L3 entity_swap extra) ──────────────────────────

_IT_SUPPORT_SYNONYMS: dict[str, list[str]] = {
    "crash":          ["segfault", "exception", "unhandled error", "core dump", "abort"],
    "segfault":       ["crash", "sigsegv", "core dump"],
    "login":          ["authenticate", "sign in", "auth", "sso"],
    "authenticate":   ["login", "sign in", "auth"],
    "billing":        ["payment", "charge", "invoice", "subscription"],
    "payment":        ["billing", "charge", "invoice"],
    "token":          ["jwt", "session", "credential", "api key"],
    "password":       ["credential", "passphrase", "secret"],
    "error":          ["exception", "failure", "fault"],
    "slow":           ["latency", "timeout", "lag", "performance"],
    "down":           ["unavailable", "unreachable", "offline", "failed"],
}


def _entity_expand(tokens: list[str], domain: str) -> list[str]:
    expanded = list(tokens)
    synonyms = _IT_SUPPORT_SYNONYMS if domain == "it_support" else {}
    for tok in tokens:
        for syn in synonyms.get(tok, []):
            syn_tokens = _tokenize(syn)
            expanded.extend(syn_tokens)
    return expanded
