"""Corpus loading, tokenization, BM25 indexing, and DF persistence."""

from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from rank_bm25 import BM25Okapi

try:
    import nltk
except ImportError:  # pragma: no cover - requirements should install nltk.
    nltk = None


TOKEN_RE = re.compile(r"\b\w+\b", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Tokenize text for BM25 and DF counting.

    Rules: lowercase, minimum token length 2, keep only tokens containing at
    least one alphanumeric character. Prefer nltk.word_tokenize when its local
    data is available; fall back to a deterministic regex tokenizer so scripts
    still work in fresh offline environments.
    """
    if not text:
        return []

    lowered = text.lower()
    raw_tokens: list[str]
    if nltk is not None:
        try:
            raw_tokens = nltk.word_tokenize(lowered)
        except LookupError:
            raw_tokens = TOKEN_RE.findall(lowered)
    else:
        raw_tokens = TOKEN_RE.findall(lowered)

    return [
        token
        for token in raw_tokens
        if len(token) >= 2 and any(char.isalnum() for char in token)
    ]


@dataclass
class CorpusIndex:
    """Pickleable BM25 index plus article metadata and document frequencies."""

    articles: list[dict[str, Any]]
    tokenized_corpus: list[list[str]]
    df_counter: Counter[str]
    bm25: BM25Okapi

    @classmethod
    def from_jsonl(cls, corpus_path: str | Path) -> "CorpusIndex":
        articles = load_jsonl(corpus_path)
        tokenized_corpus: list[list[str]] = []
        df_counter: Counter[str] = Counter()

        for article in articles:
            index_text = article.get("enriched_body") or article.get("body") or ""
            tokens = tokenize(" ".join([str(article.get("title", "")), str(index_text)]))
            tokenized_corpus.append(tokens)

            document_terms = set(tokens)
            enriched_terms = article.get("enriched_terms") or []
            if isinstance(enriched_terms, list):
                document_terms.update(term for term in enriched_terms if isinstance(term, str))
            df_counter.update(document_terms)

        return cls(
            articles=articles,
            tokenized_corpus=tokenized_corpus,
            df_counter=df_counter,
            bm25=BM25Okapi(tokenized_corpus),
        )

    @property
    def size(self) -> int:
        return len(self.articles)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        query_tokens = tokenize(query)
        return self.search_tokens(query_tokens, top_k=top_k)

    def search_tokens(self, query_tokens: Iterable[str], top_k: int = 5) -> list[dict[str, Any]]:
        tokens = list(query_tokens)
        if not tokens or self.size == 0:
            return []

        scores = self.bm25.get_scores(tokens)
        ranked_indices = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)

        results: list[dict[str, Any]] = []
        for rank, idx in enumerate(ranked_indices[:top_k], start=1):
            article = self.articles[idx]
            body = str(article.get("body", ""))
            results.append(
                {
                    "rank": rank,
                    "id": article.get("id"),
                    "title": article.get("title", ""),
                    "score": float(scores[idx]),
                    "snippet": make_snippet(body),
                }
            )
        return results


def make_snippet(body: str, max_chars: int = 180) -> str:
    normalized = " ".join(body.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "..."


def load_jsonl(corpus_path: str | Path) -> list[dict[str, Any]]:
    path = Path(corpus_path)
    articles: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            article = json.loads(stripped)
            validate_article(article, path, line_number)
            articles.append(article)

    if not articles:
        raise ValueError(f"{path} contains no KB articles")
    return articles


def validate_article(article: dict[str, Any], path: Path, line_number: int) -> None:
    missing = [field for field in ("id", "title", "body") if field not in article]
    if missing:
        missing_fields = ", ".join(missing)
        raise ValueError(f"{path}:{line_number} missing required field(s): {missing_fields}")


def save_df_store(df_counter: Counter[str], output_path: str | Path) -> Path:
    df_path = Path(output_path)
    serializable = {term: int(df_counter[term]) for term in sorted(df_counter)}
    with df_path.open("w", encoding="utf-8") as handle:
        json.dump(serializable, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return df_path


def build_and_save(corpus_path: str | Path, output_path: str | Path) -> CorpusIndex:
    index = CorpusIndex.from_jsonl(corpus_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        pickle.dump(index, handle)

    save_df_store(index.df_counter, output.parent / "df_store.json")
    return index


def load_saved_index(index_path: str | Path) -> CorpusIndex:
    with Path(index_path).open("rb") as handle:
        loaded = pickle.load(handle)
    if not isinstance(loaded, CorpusIndex):
        raise TypeError(f"{index_path} did not contain a CorpusIndex")
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a BM25 index from a KB JSONL corpus.")
    parser.add_argument("corpus", help="Path to KB corpus JSONL")
    parser.add_argument("--output", default="data/bm25_index.pkl", help="Index pickle output path")
    args = parser.parse_args()

    index = build_and_save(args.corpus, args.output)
    df_path = Path(args.output).parent / "df_store.json"
    print(f"indexed_articles={index.size}")
    print(f"index={args.output}")
    print(f"df_store={df_path}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from src.index import main as module_main

    module_main()
