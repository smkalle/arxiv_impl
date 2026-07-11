"""Contract-layer tests: validate_inputs/validate_outputs positive + negative for every adapter."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from metaorch.adapters import default_adapters
from metaorch.errors import ContractError


VALID_RUN_REQUESTS: dict[str, dict[str, Any]] = {
    "INGEST": {
        "source_path": "fixtures/z.csv",
        "source_type": "zendesk",
        "batch_size": 128,
        "embed_model": "all-MiniLM-L6-v2",
    },
    "KB_ENRICH": {
        "kb_articles": [
            {
                "article_id": "kb-1",
                "title": "title one two three",
                "body": "body",
                "product_area": "identity",
                "last_updated": "2026-04-01T00:00:00Z",
            }
        ],
        "ollama_model": "qwen2.5:3b",
        "tau": 0.01,
        "weight_w": 1.5,
    },
    "MM_SEARCH": {
        "query_text": "how do I reset MFA?",
        "n_results": 5,
        "modality_filter": ["text"],
        "source_filter": [],
        "acl_groups": ["eng-all"],
    },
    "RETRIEVE": {
        "ticket_text": "reset MFA identity",
        "top_k": 3,
        "tau": 0.01,
        "weight_w": 1.5,
        "corpus": [
            {
                "article_id": "kb-1",
                "title": "title",
                "enriched_body": "reset MFA identity authenticator",
                "enriched_terms": ["reset", "MFA", "identity", "authenticator"],
            }
        ],
    },
    "TICKETMIND": {
        "ticket_text": "how do I reset MFA?",
        "top_k": 3,
        "filters": {"product_area": None, "date_from": None},
        "session_id": "s1",
    },
    "CATALOG": {
        "sku_ids": ["RAK-TEST-001"],
        "sources": ["gs1"],
        "min_delta_threshold": 2.0,
        "dry_run": False,
    },
    "EVOLVE": {
        "start_from": "L1",
        "baseline_f1": 0.34,
        "max_rounds": 7,
    },
    "COEVOLVE": {
        "mode": "rqgm",
        "budget": 80,
        "checkpoint": 30,
        "task_set": "tasks/humaneval_20.json",
    },
}


def _get(adapters: dict, stage: str):
    return adapters[next(s for s in adapters if s.value == stage)]


@pytest.mark.parametrize("stage,inputs", list(VALID_RUN_REQUESTS.items()))
def test_validate_inputs_positive(stage: str, inputs: dict[str, Any]) -> None:
    adapter = _get(default_adapters(), stage)
    adapter.validate_inputs(inputs)  # must not raise


@pytest.mark.parametrize("stage", VALID_RUN_REQUESTS.keys())
def test_validate_inputs_negative_missing_key(stage: str) -> None:
    adapter = _get(default_adapters(), stage)
    inputs = copy.deepcopy(VALID_RUN_REQUESTS[stage])
    del inputs[next(iter(inputs))]
    with pytest.raises(ContractError):
        adapter.validate_inputs(inputs)


@pytest.mark.parametrize("stage,inputs", list(VALID_RUN_REQUESTS.items()))
def test_validate_outputs_positive(stage: str, inputs: dict[str, Any]) -> None:
    adapter = _get(default_adapters(), stage)
    adapter.validate_inputs(inputs)
    outputs = adapter.run(inputs, {})
    adapter.validate_outputs(outputs)  # must not raise


def test_catalog_dry_run_blocks_manifests() -> None:
    cat = _get(default_adapters(), "CATALOG")
    inputs = {**VALID_RUN_REQUESTS["CATALOG"], "dry_run": True}
    cat.validate_inputs(inputs)
    out = cat.run(inputs, {})
    cat.validate_outputs(out)
    assert out["manifests_committed"] == 0
    assert out["avg_score_delta"] is None
    assert out["skus_enriched"] == 0


def test_retrieve_fallback_set_implies_reason() -> None:
    sira = _get(default_adapters(), "RETRIEVE")
    inputs = {
        "ticket_text": "a b c d",  # none longer than 5 chars -> empty sketch -> fallback
        "top_k": 3,
        "tau": 0.01,
        "weight_w": 1.5,
        "corpus": VALID_RUN_REQUESTS["RETRIEVE"]["corpus"],
    }
    sira.validate_inputs(inputs)
    out = sira.run(inputs, {})
    sira.validate_outputs(out)
    assert out["fallback_used"] is True
    assert "fallback_reason" in out
    # rejected must be a subset of generated (headline invariant).
    assert set(out["sketch_terms_rejected"]).issubset(set(out["sketch_terms_generated"]))


def test_co_evolve_rqgm_satisfies_p0_less_tokens_than_baseline() -> None:
    rgqm = _get(default_adapters(), "COEVOLVE")
    inputs = VALID_RUN_REQUESTS["COEVOLVE"]
    rgqm.validate_inputs(inputs)
    out = rgqm.run(inputs, {})
    rgqm.validate_outputs(out)
    assert out["erasure_invariant_holds"] is True
    assert out["blended_tokens"] <= out["baseline_tokens"]
    # Exactly one epoch-boundary event (rqgm contract).
    boundary = [e for e in out["epoch_events"] if "epoch" in (e.get("action") or "")]
    assert len(boundary) == 1


def test_co_evolve_hgm_h_has_no_epoch_event() -> None:
    rgqm = _get(default_adapters(), "COEVOLVE")
    inputs = {**VALID_RUN_REQUESTS["COEVOLVE"], "mode": "hgm_h"}
    rgqm.validate_inputs(inputs)
    out = rgqm.run(inputs, {})
    rgqm.validate_outputs(out)
    assert out["epoch_events"] == []
    assert out["blended_tokens"] == out["baseline_tokens"]


def test_co_evolve_rqgm_rejects_two_epoch_events() -> None:
    rgqm = _get(default_adapters(), "COEVOLVE")
    out = rgqm.run(VALID_RUN_REQUESTS["COEVOLVE"], {})
    out["epoch_events"].append({"step": 50, "action": "epoch_boundary_secondary", "promoted": True})
    with pytest.raises(ContractError):
        rgqm.validate_outputs(out)


def test_co_evolve_rejects_checkpoint_exceeding_budget() -> None:
    rgqm = _get(default_adapters(), "COEVOLVE")
    with pytest.raises(ContractError):
        rgqm.validate_inputs({"mode": "rqgm", "budget": 10, "checkpoint": 50, "task_set": "t.json"})


def test_evolve_baseline_when_no_patches_accepted() -> None:
    ev = _get(default_adapters(), "EVOLVE")
    # Run only L1 (i=0 -> no patches) so final_config_version=baseline.
    inputs = {"start_from": "L1", "baseline_f1": 0.34, "max_rounds": 1, "only": "L1"}
    ev.validate_inputs(inputs)
    out = ev.run(inputs, {})
    ev.validate_outputs(out)
    assert out["final_config_version"] == "baseline"


def test_evolve_evolved_implies_at_least_one_patch() -> None:
    ev = _get(default_adapters(), "EVOLVE")
    inputs = {"start_from": "L2", "baseline_f1": 0.20, "max_rounds": 7}
    ev.validate_inputs(inputs)
    out = ev.run(inputs, {})
    ev.validate_outputs(out)
    if out["final_config_version"] == "evolved":
        assert any(lr["accepted_patches"] for lr in out["loop_results"])


def test_mm_search_rejects_score_out_of_range() -> None:
    jina = _get(default_adapters(), "MM_SEARCH")
    out = jina.run(VALID_RUN_REQUESTS["MM_SEARCH"], {})
    out["results"][0]["score"] = 1.5  # out of [0,1]
    with pytest.raises(ContractError):
        jina.validate_outputs(out)


def test_ticketmind_rejects_negative_view_contribution() -> None:
    tk = _get(default_adapters(), "TICKETMIND")
    out = tk.run(VALID_RUN_REQUESTS["TICKETMIND"], {})
    out["results"][0]["view_contributions"]["semantic"] = -0.1
    with pytest.raises(ContractError):
        tk.validate_outputs(out)