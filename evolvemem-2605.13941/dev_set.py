"""
Dev set builder and evaluator.

dev_set.py builds dev_set.json (150 train pairs) and test_set.json (50 held-out)
from resolved_tickets.csv.

DevSetEvaluator.compute_f1() is the fitness oracle used by L1, L3, and L4.
L1 evolves DevSetConfig parameters to maximize F1 gain.
"""
from __future__ import annotations

import csv
import dataclasses
import json
import random
from pathlib import Path
from typing import Any


@dataclasses.dataclass
class DevSetConfig:
    """L1's edit target: sampling strategy for the dev set."""
    min_csat: int = 4
    n_train: int = 150
    n_test: int = 50
    vocab_gap_ratio: float = 0.0       # fraction of pairs with zero lexical overlap
    augmentation_strategy: str = "none"
    random_seed: int = 42

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DevSetConfig":
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in valid})

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class DevPair:
    ticket_id: str
    ticket_text: str
    ground_truth_kb_id: str
    product_area: str
    csat_score: int

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# ── Build dev/test sets ──────────────────────────────────────────────────────

def build_dev_set(
    tickets_csv: Path,
    dev_set_path: Path,
    test_set_path: Path,
    config: DevSetConfig | None = None,
) -> tuple[list[DevPair], list[DevPair]]:
    """Build train/test splits from resolved_tickets.csv."""
    cfg = config or DevSetConfig()
    rng = random.Random(cfg.random_seed)

    all_pairs: list[DevPair] = []
    with open(tickets_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                csat = int(row.get("csat_score", "0") or "0")
            except ValueError:
                csat = 0
            if csat < cfg.min_csat:
                continue
            all_pairs.append(DevPair(
                ticket_id=row.get("ticket_id", ""),
                ticket_text=row.get("ticket_text", ""),
                ground_truth_kb_id=row.get("ground_truth_kb_id", ""),
                product_area=row.get("product_area", ""),
                csat_score=csat,
            ))

    rng.shuffle(all_pairs)

    n_test = min(cfg.n_test, len(all_pairs) // 4)
    n_train = min(cfg.n_train, len(all_pairs) - n_test)

    test_pairs = all_pairs[:n_test]
    train_pairs = all_pairs[n_test: n_test + n_train]

    dev_set_path.parent.mkdir(parents=True, exist_ok=True)
    dev_set_path.write_text(json.dumps([p.to_dict() for p in train_pairs], indent=2))
    test_set_path.write_text(json.dumps([p.to_dict() for p in test_pairs], indent=2))

    return train_pairs, test_pairs


# ── Evaluator ────────────────────────────────────────────────────────────────

class DevSetEvaluator:
    """
    Computes F1@top_k for a router + RetrievalConfig pair.
    Used by L1, L3, and L4 as the fitness oracle.
    """

    def __init__(
        self,
        dev_set_path: Path,
        config: DevSetConfig | None = None,
    ) -> None:
        self._all_pairs: list[DevPair] = []
        if dev_set_path.exists():
            raw = json.loads(dev_set_path.read_text())
            self._all_pairs = [
                DevPair(**p) if isinstance(p, dict) else p for p in raw
            ]
        self._config = config or DevSetConfig()
        self._sampled: list[DevPair] = list(self._all_pairs)

    def sample(self) -> list[DevPair]:
        rng = random.Random(self._config.random_seed)
        pairs = list(self._all_pairs)
        rng.shuffle(pairs)
        self._sampled = pairs[: self._config.n_train]
        return self._sampled

    def compute_f1(self, router: Any, retrieval_config: Any) -> float:
        """Return mean F1@k across the sampled query set."""
        pairs = self._sampled or self._all_pairs
        if not pairs:
            return 0.0

        top_k = getattr(retrieval_config, "top_k", 5)
        f1_scores: list[float] = []

        for pair in pairs:
            try:
                results = router.ask(
                    query=pair.ticket_text,
                    config=retrieval_config,
                )
            except Exception:
                f1_scores.append(0.0)
                continue

            retrieved_ids = {r.get("article_id", "") for r in results[:top_k]}
            gt_id = pair.ground_truth_kb_id
            relevant = {gt_id} if gt_id else set()

            if not relevant:
                continue

            hits = len(retrieved_ids & relevant)
            precision = hits / len(retrieved_ids) if retrieved_ids else 0.0
            recall = hits / len(relevant)
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
            f1_scores.append(f1)

        return sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

    @property
    def pairs(self) -> list[DevPair]:
        return self._sampled or self._all_pairs


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from config import KB_ARTICLES_CSV, RESOLVED_TICKETS_CSV, DEV_SET_JSON, TEST_SET_JSON, DEV_SET_DEFAULTS

    cfg = DevSetConfig(**DEV_SET_DEFAULTS)
    train, test = build_dev_set(RESOLVED_TICKETS_CSV, DEV_SET_JSON, TEST_SET_JSON, cfg)
    print(f"Dev set: {len(train)} train pairs, {len(test)} test pairs written.")
    print(f"  → {DEV_SET_JSON}")
    print(f"  → {TEST_SET_JSON}")
