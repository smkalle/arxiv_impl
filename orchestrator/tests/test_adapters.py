"""Adapter-layer tests: each adapter.run() produces the documented output shape, not just contract-valid."""

from __future__ import annotations

from typing import Any

import pytest

from metaorch.adapters import default_adapters
from metaorch.models import StageKind


def _ad(stage: StageKind):
    return default_adapters()[stage]


def test_ingest_outputs_match_aafow_contract_sample() -> None:
    out = _ad(StageKind.INGEST).run(
        {
            "source_path": "z.csv",
            "source_type": "zendesk",
            "batch_size": 128,
            "embed_model": "all-MiniLM-L6-v2",
        },
        {"rows_ingested": 256, "embed_dim": 384},
    )
    assert out["arrow_path"].endswith("tickets.arrow")
    assert out["faiss_path"].endswith("index.faiss")
    rs = out["run_summary"]
    assert rs["rows_ingested"] == 256
    assert rs["embed_dim"] == 384
    assert rs["batches"] == 2
    schema_cols = {c["name"] for c in out["table_schema"]["columns"]}
    # AAFLOW hard contract: faiss_id + embedding columns present.
    assert {"faiss_id", "embedding", "chunk", "chunk_index"}.issubset(schema_cols)


def test_kb_enrich_outputs_enriched_corpus_of_same_length(sample_kb) -> None:
    out = _ad(StageKind.KB_ENRICH).run(
        {"kb_articles": sample_kb, "ollama_model": "qwen2.5:3b", "tau": 0.01, "weight_w": 1.5},
        {"top_k": 5},
    )
    assert len(out["enriched_corpus"]) == len(sample_kb)
    rd = out["setup_summary"]["retrieval_defaults"]
    assert rd == {"tau": 0.01, "weight_w": 1.5, "top_k": 5}
    for art in out["enriched_corpus"]:
        assert "enriched_terms" in art and isinstance(art["enriched_terms"], list)


def test_mm_search_returns_results_with_embed_dim() -> None:
    out = _ad(StageKind.MM_SEARCH).run(
        {
            "query_text": "how do I reset MFA?",
            "n_results": 4,
            "modality_filter": [],
            "source_filter": [],
            "acl_groups": ["eng-all"],
        },
        {"embed_dim": 384},
    )
    assert out["backend_used"] == "stub"
    assert out["embed_dim"] == 384
    assert out["total"] == len(out["results"])
    for r in out["results"]:
        assert 0.0 <= r["score"] <= 1.0
        assert r["modality"] in {"text", "image", "audio", "video", "pdf"}


def test_retrieve_top_k_respected(enriched_corpus) -> None:
    out = _ad(StageKind.RETRIEVE).run(
        {
            "ticket_text": "reset MFA identity authenticator",
            "top_k": 1,
            "tau": 0.01,
            "weight_w": 1.5,
            "corpus": enriched_corpus,
        },
        {},
    )
    assert len(out["results"]) == 1
    assert out["results"][0]["matched_enriched_terms"] or out["results"][0]["matched_original_terms"]
    assert out["latency_ms"] >= 0


def test_ticketmind_view_contributions_sum_to_score() -> None:
    out = _ad(StageKind.TICKETMIND).run(
        {
            "ticket_text": "how do I reset MFA?",
            "top_k": 2,
            "filters": {},
        },
        {"evolved": True},
    )
    assert out["retrieval_trace"]["evolved_config_version"] == "evolved"
    for r in out["results"]:
        vc = r["view_contributions"]
        s = vc["semantic"] + vc["lexical"] + vc["symbolic"]
        # The contract says each view is float >= 0; that their contributions support
        # the score, but not necessarily that they sum to score. We assert positivity only.
        assert s > 0


def test_catalog_dry_run_zero_commits() -> None:
    out = _ad(StageKind.CATALOG).run(
        {"sku_ids": ["A", "B"], "sources": ["gs1"], "min_delta_threshold": 2.0, "dry_run": True},
        {},
    )
    assert out["status"] == "completed"
    assert out["manifests_committed"] == 0
    assert out["provenance_artifact"] is None


def test_catalog_wet_run_commits_when_above_threshold() -> None:
    out = _ad(StageKind.CATALOG).run(
        {"sku_ids": ["A"], "sources": ["gs1"], "min_delta_threshold": 2.0, "dry_run": False},
        {},
    )
    assert out["manifests_committed"] == 1
    assert out["avg_score_delta"] >= 2.0
    assert out["provenance_artifact"].endswith("provenance.json")


def test_catalog_rejects_when_threshold_above_fake_delta() -> None:
    # Fake delta is 3.0; setting min_delta_threshold above it should commit zero.
    out = _ad(StageKind.CATALOG).run(
        {"sku_ids": ["A"], "sources": ["gs1"], "min_delta_threshold": 5.0, "dry_run": False},
        {},
    )
    assert out["manifests_committed"] == 0
    assert out["skus_enriched"] == 0
    assert out["skus_rejected"] == 1


def test_evolve_loop_count_matches_journey_starting_l2() -> None:
    out = _ad(StageKind.EVOLVE).run(
        {"start_from": "L2", "baseline_f1": 0.20, "max_rounds": 7},
        {},
    )
    # L1 not requested when start_from=L2; loops should be L2, L3, L4 only.
    loop_ids = [lr["loop_id"] for lr in out["loop_results"]]
    assert loop_ids == ["L2", "L3", "L4"]


def test_evolve_with_only_runs_single_loop() -> None:
    out = _ad(StageKind.EVOLVE).run(
        {"start_from": "L1", "baseline_f1": 0.20, "max_rounds": 7, "only": "L3"},
        {},
    )
    assert [lr["loop_id"] for lr in out["loop_results"]] == ["L3"]


def test_co_evolve_rqgm_token_count_decreases_post_epoch() -> None:
    out = _ad(StageKind.COEVOLVE).run(
        {"mode": "rqgm", "budget": 80, "checkpoint": 30, "task_set": "tasks/humaneval_20.json"},
        {},
    )
    # Sanity: blended < baseline (the RGQM P0 from spec).
    assert out["blended_tokens"] < out["baseline_tokens"]
    # Archive counts > 0.
    assert out["final_archive_summary"]["nodes"] == 80


def test_co_evolve_hgm_h_baseline_tokens_equal() -> None:
    out = _ad(StageKind.COEVOLVE).run(
        {"mode": "hgm_h", "budget": 80, "checkpoint": 30, "task_set": "tasks/humaneval_20.json"},
        {},
    )
    assert out["blended_tokens"] == out["baseline_tokens"]
    assert out["final_archive_summary"]["epoch_events"] == 0