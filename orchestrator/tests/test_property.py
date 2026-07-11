"""Property-based / randomized / fuzz tests using hypothesis.

Hypothesis is optional; if not installed, the module is skipped.
"""

from __future__ import annotations

import string
import sys
from typing import Any

import pytest

try:
    from hypothesis import HealthCheck, given, settings, strategies as st
    HAVE_HYPOTHESIS = True
except ImportError:  # pragma: no cover
    HAVE_HYPOTHESIS = False


pytestmark = pytest.mark.skipif(not HAVE_HYPOTHESIS,
                                reason="hypothesis not installed (optional dep)")


if HAVE_HYPOTHESIS:
    from metaorch.adapters import default_adapters
    from metaorch.contract import CANONICAL_FULL_RUN, PIPELINE_DAG
    from metaorch.executor import PipelineExecutor, topo_order
    from metaorch.models import PipelineContext, RunPlan, StageKind

    # --- Strategies ----------------------------------------------------------

    ticket_text_st = st.text(alphabet=string.ascii_letters + string.digits + " ", min_size=0, max_size=200)

    kb_article_st = st.fixed_dictionaries({
        "article_id": st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20),
        "title": st.text(alphabet=string.ascii_letters + " ", min_size=1, max_size=40),
        "body": st.text(alphabet=string.ascii_letters + " ", min_size=1, max_size=200),
        "product_area": st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=10),
        "last_updated": st.just("2026-04-01T00:00:00Z"),
    })

    @given(ticket=ticket_text_st, top_k=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_retrieve_never_returns_more_than_top_k(ticket: str, top_k: int,
                                                   enriched_corpus) -> None:
        adapter = default_adapters()[StageKind.RETRIEVE]
        inputs = {
            "ticket_text": ticket or "x",  # validate_inputs requires non-empty str
            "top_k": top_k,
            "tau": 0.01,
            "weight_w": 1.5,
            "corpus": enriched_corpus,
        }
        adapter.validate_inputs(inputs)
        out = adapter.run(inputs, {})
        adapter.validate_outputs(out)
        assert len(out["results"]) <= top_k
        # Subset invariant for sketch terms.
        assert set(out["sketch_terms_rejected"]).issubset(set(out["sketch_terms_generated"]))

    @given(kb=st.lists(kb_article_st, min_size=1, max_size=20))
    @settings(max_examples=30, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_kb_enrich_corpus_length_equals_input(kb: list[dict[str, Any]]) -> None:
        adapter = default_adapters()[StageKind.KB_ENRICH]
        inputs = {"kb_articles": kb, "ollama_model": "qwen2.5:3b", "tau": 0.01, "weight_w": 1.5}
        adapter.validate_inputs(inputs)
        out = adapter.run(inputs, {})
        adapter.validate_outputs(out)
        assert len(out["enriched_corpus"]) == len(kb)

    @given(mode=st.sampled_from(["rqgm", "hgm_h"]),
           budget=st.integers(min_value=1, max_value=200),
           frac=st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=40, deadline=None)
    def test_co_evolve_contract_holds_for_any_budget(mode: str, budget: int, frac: float) -> None:
        checkpoint = int(frac * budget) if budget > 0 else 0
        adapter = default_adapters()[StageKind.COEVOLVE]
        inputs = {"mode": mode, "budget": budget, "checkpoint": checkpoint,
                  "task_set": "tasks/humaneval_20.json"}
        adapter.validate_inputs(inputs)
        out = adapter.run(inputs, {})
        adapter.validate_outputs(out)
        if mode == "rqgm":
            assert out["blended_tokens"] <= out["baseline_tokens"]
            assert out["erasure_invariant_holds"] is True
        else:
            assert out["blended_tokens"] == out["baseline_tokens"]
        assert out["final_archive_summary"]["nodes"] == budget

    @given(stage_subset=st.lists(st.sampled_from(list(StageKind)), min_size=0, max_size=8, unique=True))
    @settings(max_examples=60, deadline=None)
    def test_topo_order_respects_all_hard_deps(stage_subset: list[StageKind]) -> None:
        if not stage_subset:
            return
        try:
            order = topo_order(stage_subset)
        except Exception:
            return  # invalid plans legitimately rejected
        pos = {s: i for i, s in enumerate(order)}
        for s in order:
            for dep in PIPELINE_DAG[s]:
                if dep in pos:
                    assert pos[dep] < pos[s], f"{dep} should precede {s}"