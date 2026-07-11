"""Negative-path tests: malformed inputs, wrong types, out-of-range values, empty data.

Each test asserts a specific ContractError is raised — these guards are the contract surface
that prevents garbage into the executor.
"""

from __future__ import annotations

from typing import Any

import pytest

from metaorch.adapters import default_adapters
from metaorch.errors import ContractError
from metaorch.models import StageKind


def _ad(stage: StageKind):
    return default_adapters()[stage]


# --- INGEST ---------------------------------------------------------------

def test_ingest_rejects_unknown_source_type() -> None:
    with pytest.raises(ContractError, match="source_type"):
        _ad(StageKind.INGEST).validate_inputs({
            "source_path": "x.csv", "source_type": "github",  # not zendesk|jira
            "batch_size": 64, "embed_model": "m",
        })


def test_ingest_rejects_zero_batch_size() -> None:
    with pytest.raises(ContractError, match="batch_size"):
        _ad(StageKind.INGEST).validate_inputs({
            "source_path": "x.csv", "source_type": "zendesk",
            "batch_size": 0, "embed_model": "m",
        })


def test_ingest_rejects_missing_embed_dim_in_summary() -> None:
    adapter = _ad(StageKind.INGEST)
    out = adapter.run({
        "source_path": "x.csv", "source_type": "zendesk",
        "batch_size": 64, "embed_model": "m",
    }, {})
    del out["run_summary"]["embed_dim"]
    with pytest.raises(ContractError, match="embed_dim"):
        adapter.validate_outputs(out)


def test_ingest_rejects_empty_table_schema() -> None:
    adapter = _ad(StageKind.INGEST)
    out = adapter.run({
        "source_path": "x.csv", "source_type": "zendesk",
        "batch_size": 64, "embed_model": "m",
    }, {})
    out["table_schema"] = {}
    with pytest.raises(ContractError, match="table_schema"):
        adapter.validate_outputs(out)


# --- KB_ENRICH ------------------------------------------------------------

def test_kb_enrich_rejects_empty_kb_articles() -> None:
    with pytest.raises(ContractError, match="non-empty"):
        _ad(StageKind.KB_ENRICH).validate_inputs({
            "kb_articles": [], "ollama_model": "m", "tau": 0.01, "weight_w": 1.5,
        })


def test_kb_enrich_rejects_article_missing_field() -> None:
    art = {"article_id": "x", "title": "t", "body": "b", "product_area": "p"}
    # missing last_updated
    with pytest.raises(ContractError, match="last_updated"):
        _ad(StageKind.KB_ENRICH).validate_inputs({
            "kb_articles": [art], "ollama_model": "m", "tau": 0.01, "weight_w": 1.5,
        })


def test_kb_enrich_rejects_negative_tau() -> None:
    with pytest.raises(ContractError, match="tau"):
        _ad(StageKind.KB_ENRICH).validate_inputs({
            "kb_articles": [{"article_id": "x", "title": "t", "body": "b",
                             "product_area": "p", "last_updated": "z"}],
            "ollama_model": "m", "tau": -0.1, "weight_w": 1.5,
        })


def test_kb_enrich_rejects_missing_retrieval_defaults() -> None:
    adapter = _ad(StageKind.KB_ENRICH)
    out = adapter.run({
        "kb_articles": [{"article_id": "x", "title": "t", "body": "b",
                         "product_area": "p", "last_updated": "z"}],
        "ollama_model": "m", "tau": 0.01, "weight_w": 1.5,
    }, {})
    del out["setup_summary"]["retrieval_defaults"]
    with pytest.raises(ContractError, match="retrieval_defaults"):
        adapter.validate_outputs(out)


# --- MM_SEARCH ------------------------------------------------------------

def test_mm_search_rejects_negative_n_results() -> None:
    with pytest.raises(ContractError, match="n_results"):
        _ad(StageKind.MM_SEARCH).validate_inputs({
            "query_text": "q", "n_results": 0,
            "modality_filter": [], "source_filter": [], "acl_groups": [],
        })


def test_mm_search_rejects_unknown_backend() -> None:
    adapter = _ad(StageKind.MM_SEARCH)
    out = adapter.run({
        "query_text": "q", "n_results": 1,
        "modality_filter": [], "source_filter": [], "acl_groups": [],
    }, {})
    out["backend_used"] = "openai"
    with pytest.raises(ContractError, match="backend_used"):
        adapter.validate_outputs(out)


def test_mm_search_rejects_score_below_zero() -> None:
    adapter = _ad(StageKind.MM_SEARCH)
    out = adapter.run({
        "query_text": "q", "n_results": 2,
        "modality_filter": [], "source_filter": [], "acl_groups": [],
    }, {})
    out["results"][0]["score"] = -0.01
    with pytest.raises(ContractError, match="score"):
        adapter.validate_outputs(out)


def test_mm_search_rejects_unknown_modality() -> None:
    adapter = _ad(StageKind.MM_SEARCH)
    out = adapter.run({
        "query_text": "q", "n_results": 2,
        "modality_filter": [], "source_filter": [], "acl_groups": [],
    }, {})
    out["results"][0]["modality"] = "hologram"
    with pytest.raises(ContractError, match="modality"):
        adapter.validate_outputs(out)


# --- RETRIEVE -------------------------------------------------------------

def test_retrieve_rejects_rejected_terms_not_subset_of_generated() -> None:
    adapter = _ad(StageKind.RETRIEVE)
    out = adapter.run({
        "ticket_text": "reset MFA identity", "top_k": 3, "tau": 0.01, "weight_w": 1.5,
        "corpus": [{"article_id": "x", "title": "t", "enriched_body": "b",
                     "enriched_terms": ["reset", "MFA"]}],
    }, {})
    # Inject a rejected term that doesn't exist in generated.
    out["sketch_terms_rejected"] = ["frobnicate"]
    out["sketch_terms_generated"] = ["reset"]
    with pytest.raises(ContractError, match="subset"):
        adapter.validate_outputs(out)


def test_retrieve_rejects_fallback_true_without_reason() -> None:
    adapter = _ad(StageKind.RETRIEVE)
    out = adapter.run({
        "ticket_text": "reset MFA identity", "top_k": 3, "tau": 0.01, "weight_w": 1.5,
        "corpus": [{"article_id": "x", "title": "t", "enriched_body": "b",
                     "enriched_terms": ["reset", "MFA"]}],
    }, {})
    out["fallback_used"] = True
    out.pop("fallback_reason", None)
    with pytest.raises(ContractError, match="fallback_reason"):
        adapter.validate_outputs(out)


def test_retrieve_rejects_top_k_below_one() -> None:
    with pytest.raises(ContractError, match="top_k"):
        _ad(StageKind.RETRIEVE).validate_inputs({
            "ticket_text": "t", "top_k": 0, "tau": 0.01, "weight_w": 1.5,
            "corpus": [{"article_id": "x", "title": "t", "enriched_body": "b",
                         "enriched_terms": []}],
        })


def test_retrieve_rejects_empty_corpus() -> None:
    with pytest.raises(ContractError, match="non-empty"):
        _ad(StageKind.RETRIEVE).validate_inputs({
            "ticket_text": "t", "top_k": 3, "tau": 0.01, "weight_w": 1.5, "corpus": [],
        })


# --- TICKETMIND -----------------------------------------------------------

def test_ticketmind_rejects_filters_not_dict() -> None:
    with pytest.raises(ContractError, match="filters"):
        _ad(StageKind.TICKETMIND).validate_inputs({
            "ticket_text": "t", "top_k": 3, "filters": "not-a-dict",
        })


def test_ticketmind_rejects_non_string_session_id() -> None:
    with pytest.raises(ContractError, match="session_id"):
        _ad(StageKind.TICKETMIND).validate_inputs({
            "ticket_text": "t", "top_k": 3, "filters": {}, "session_id": 1234,
        })


def test_ticketmind_rejects_unknown_evolved_config_version() -> None:
    adapter = _ad(StageKind.TICKETMIND)
    out = adapter.run({"ticket_text": "t", "top_k": 1, "filters": {}}, {})
    out["retrieval_trace"]["evolved_config_version"] = "v3"
    with pytest.raises(ContractError, match="evolved_config_version"):
        adapter.validate_outputs(out)


def test_ticketmind_rejects_missing_view_contribution() -> None:
    adapter = _ad(StageKind.TICKETMIND)
    out = adapter.run({"ticket_text": "t", "top_k": 1, "filters": {}}, {})
    del out["results"][0]["view_contributions"]["symbolic"]
    with pytest.raises(ContractError, match="symbolic"):
        adapter.validate_outputs(out)


# --- CATALOG --------------------------------------------------------------

def test_catalog_rejects_dry_run_not_bool() -> None:
    with pytest.raises(ContractError, match="dry_run"):
        _ad(StageKind.CATALOG).validate_inputs({
            "sku_ids": ["A"], "sources": ["g"], "min_delta_threshold": 2.0, "dry_run": "yes",
        })


def test_catalog_rejects_negative_min_delta() -> None:
    with pytest.raises(ContractError, match="min_delta_threshold"):
        _ad(StageKind.CATALOG).validate_inputs({
            "sku_ids": ["A"], "sources": ["g"], "min_delta_threshold": -1.0, "dry_run": False,
        })


def test_catalog_rejects_unknown_status_value() -> None:
    adapter = _ad(StageKind.CATALOG)
    out = adapter.run({
        "sku_ids": ["A"], "sources": ["g"], "min_delta_threshold": 2.0, "dry_run": False,
    }, {})
    out["status"] = "exploding"
    with pytest.raises(ContractError, match="status"):
        adapter.validate_outputs(out)


def test_catalog_wet_run_with_high_threshold_rejects_all() -> None:
    # Fake delta is 3.0; threshold above that rejects all commits.
    out = _ad(StageKind.CATALOG).run({
        "sku_ids": ["A", "B"], "sources": ["g"], "min_delta_threshold": 10.0, "dry_run": False,
    }, {})
    assert out["manifests_committed"] == 0
    assert out["skus_rejected"] == 2
    assert out["skus_enriched"] == 0


# --- EVOLVE ---------------------------------------------------------------

def test_evolve_rejects_unknown_start_from() -> None:
    with pytest.raises(ContractError, match="start_from"):
        _ad(StageKind.EVOLVE).validate_inputs({
            "start_from": "L5", "baseline_f1": 0.1, "max_rounds": 3,
        })


def test_evolve_rejects_negative_baseline_f1() -> None:
    with pytest.raises(ContractError, match="baseline_f1"):
        _ad(StageKind.EVOLVE).validate_inputs({
            "start_from": "L1", "baseline_f1": -0.1, "max_rounds": 3,
        })


def test_evolve_rejects_unknown_only() -> None:
    with pytest.raises(ContractError, match="only"):
        _ad(StageKind.EVOLVE).validate_inputs({
            "start_from": "L1", "baseline_f1": 0.1, "max_rounds": 3, "only": "L5",
        })


def test_evolve_rejects_evolved_without_any_patches() -> None:
    adapter = _ad(StageKind.EVOLVE)
    out = adapter.run({"start_from": "L2", "baseline_f1": 0.1, "max_rounds": 7}, {})
    # Force evolved version but strip every accepted_patches list.
    out["final_config_version"] = "evolved"
    for lr in out["loop_results"]:
        lr["accepted_patches"] = []
    with pytest.raises(ContractError, match="accepted_patches"):
        adapter.validate_outputs(out)


def test_evolve_rejects_negative_fitness_gain() -> None:
    adapter = _ad(StageKind.EVOLVE)
    out = adapter.run({"start_from": "L1", "baseline_f1": 0.5, "max_rounds": 7}, {})
    out["fitness_gain"] = -0.01
    with pytest.raises(ContractError, match="fitness_gain"):
        adapter.validate_outputs(out)


# --- COEVOLVE --------------------------------------------------------------

def test_co_evolve_rejects_unknown_mode() -> None:
    with pytest.raises(ContractError, match="mode"):
        _ad(StageKind.COEVOLVE).validate_inputs({
            "mode": "alpha_go", "budget": 80, "checkpoint": 30, "task_set": "t.json",
        })


def test_co_evolve_rejects_zero_budget() -> None:
    with pytest.raises(ContractError, match="budget"):
        _ad(StageKind.COEVOLVE).validate_inputs({
            "mode": "rqgm", "budget": 0, "checkpoint": 0, "task_set": "t.json",
        })


def test_co_evolve_rejects_checkpoint_above_budget() -> None:
    with pytest.raises(ContractError, match="checkpoint"):
        _ad(StageKind.COEVOLVE).validate_inputs({
            "mode": "rqgm", "budget": 10, "checkpoint": 20, "task_set": "t.json",
        })


def test_co_evolve_rejects_rqgm_with_false_erasure_invariant() -> None:
    adapter = _ad(StageKind.COEVOLVE)
    out = adapter.run({
        "mode": "rqgm", "budget": 80, "checkpoint": 30, "task_set": "t.json",
    }, {})
    out["erasure_invariant_holds"] = False
    with pytest.raises(ContractError, match="erasure_invariant"):
        adapter.validate_outputs(out)


def test_co_evolve_rejects_rqgm_with_blended_above_baseline() -> None:
    adapter = _ad(StageKind.COEVOLVE)
    out = adapter.run({
        "mode": "rqgm", "budget": 80, "checkpoint": 30, "task_set": "t.json",
    }, {})
    out["blended_tokens"] = out["baseline_tokens"] + 1000
    with pytest.raises(ContractError, match="blended_tokens"):
        adapter.validate_outputs(out)


def test_co_evolve_rejects_zero_epoch_events_for_rqgm() -> None:
    adapter = _ad(StageKind.COEVOLVE)
    out = adapter.run({
        "mode": "rqgm", "budget": 80, "checkpoint": 30, "task_set": "t.json",
    }, {})
    out["epoch_events"] = []  # rqgm must have exactly one boundary event
    with pytest.raises(ContractError, match="epoch-boundary"):
        adapter.validate_outputs(out)