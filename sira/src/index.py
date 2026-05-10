import argparse
import json
import pickle
from collections import Counter
from pathlib import Path
from typing import Optional

import nltk
from rank_bm25 import BM25Okapi

nltk.download("punkt_tab", quiet=True)


def read_jsonl(path: str | Path) -> list[dict]:
    articles = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                articles.append(json.loads(line))
    return articles


def tokenize(text: str) -> list[str]:
    tokens = nltk.word_tokenize(text.lower())
    return [t for t in tokens if len(t) >= 2 and any(c.isalnum() for c in t)]


class CorpusIndex:
    def __init__(self):
        self.articles: list[dict] = []
        self.tokenized: list[list[str]] = []
        self.bm25: Optional[BM25Okapi] = None
        self.df_counter: Counter = Counter()

    def load_corpus(self, corpus_path: str | Path) -> None:
        articles = read_jsonl(corpus_path)

        if not articles:
            raise ValueError(f"No articles found in {corpus_path}")

        for art in articles:
            body = art.get("enriched_body") or art.get("body", "")
            if not body.strip():
                raise ValueError(f"Empty body in article {art.get('article_id')}")

        self.articles = articles
        self.tokenized = [
            tokenize(a["title"] + " " + (a.get("enriched_body") or a.get("body", "")))
            for a in articles
        ]
        self.bm25 = BM25Okapi(self.tokenized)

        self.df_counter = Counter()
        for i, doc_tokens in enumerate(self.tokenized):
            doc_terms = set(doc_tokens)
            for term in self.articles[i].get("enriched_terms", []):
                doc_terms.add(term.lower())
            for t in doc_terms:
                self.df_counter[t] += 1

    def save(self, index_path: str | Path) -> None:
        Path(index_path).parent.mkdir(parents=True, exist_ok=True)
        with open(index_path, "wb") as f:
            pickle.dump(self, f)

    def save_df_store(self, df_store_path: str | Path) -> None:
        Path(df_store_path).parent.mkdir(parents=True, exist_ok=True)
        with open(df_store_path, "w") as f:
            json.dump(dict(self.df_counter), f)

    @classmethod
    def load(cls, index_path: str | Path) -> "CorpusIndex":
        with open(index_path, "rb") as f:
            return pickle.load(f)


def build_and_save(
    corpus_path: str | Path,
    index_path: str | Path,
    df_store_path: str | Path | None = None,
) -> CorpusIndex:
    idx = CorpusIndex()
    idx.load_corpus(corpus_path)
    idx.save(index_path)
    if df_store_path is None:
        df_store_path = Path(index_path).parent / "df_store.json"
    idx.save_df_store(df_store_path)
    return idx


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build BM25 index from KB corpus")
    parser.add_argument("corpus", help="Path to kb_corpus.jsonl")
    parser.add_argument("--output", default="data/bm25_index.pkl", help="Output index path")
    args = parser.parse_args()

    idx = build_and_save(args.corpus, args.output)
    print(f"Built index: {len(idx.articles)} articles, {len(idx.df_counter)} unique terms")
    print(f"Saved to {args.output}")
    print(f"DF store saved to {Path(args.output).parent / 'df_store.json'}")
