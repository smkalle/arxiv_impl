import tempfile
import pytest
import os
import json

from agents import ReviewerAgent
from search import run_epoch_boundary
import search
from archive import Archive, _new_node
import llm


def _seed():
    arc = Archive()
    root = _new_node(coder_fn="c0", reviewer_fn="r0")
    arc.add_node(root)
    child = _new_node(coder_fn="c1", reviewer_fn="r1")
    arc.add_child(root["id"], child)
    return arc, root, child


def test_selective_erase_removes_only_reviewer_epoch0():
    arc, root, child = _seed()
    arc.record(root["id"], "coder", "t1", 1, 0, is_verifiable=True)
    arc.record(root["id"], "reviewer", "t1", 1, 0, is_verifiable=False)
    arc.record(child["id"], "reviewer", "t2", 0, 0, is_verifiable=False)
    arc.record(child["id"], "coder", "t2", 1, 0, is_verifiable=True)

    erased = arc.selective_erase(role="reviewer", epoch=0)

    assert erased == 2
    stale = [r for r in arc.utility_records
             if r["role"] == "reviewer" and r["epoch"] == 0]
    assert len(stale) == 0


def test_coder_records_survive_erasure():
    arc, root, child = _seed()
    arc.record(root["id"], "coder", "t1", 1, 0, is_verifiable=True)
    arc.record(child["id"], "coder", "t2", 0, 0, is_verifiable=True)
    arc.record(root["id"], "reviewer", "t1", 1, 0, is_verifiable=False)

    arc.selective_erase(role="reviewer", epoch=0)

    coder = [r for r in arc.utility_records if r["role"] == "coder"]
    assert len(coder) == 2
    assert all(r["is_verifiable"] for r in coder)


def test_erasure_refuses_to_delete_verifiable_records():
    arc, root, child = _seed()
    arc.record(root["id"], "coder", "t1", 1, 0, is_verifiable=True)

    arc.utility_records.append({
        "id": "x", "node_id": root["id"], "role": "reviewer",
        "task_id": "t1", "outcome": 1, "epoch": 0,
        "is_verifiable": True, "reviewer_output_cache": None,
    })
    with pytest.raises(AssertionError):
        arc.selective_erase(role="reviewer", epoch=0)


def test_clade_aggregates_recomputed_after_erasure():
    arc, root, child = _seed()
    arc.record(child["id"], "coder", "t1", 1, 0, is_verifiable=True)
    arc.record(child["id"], "coder", "t2", 0, 0, is_verifiable=True)
    arc.record(child["id"], "reviewer", "t1", 1, 0, is_verifiable=False)

    arc.selective_erase(role="reviewer", epoch=0)

    root = arc.get(root["id"])
    child = arc.get(child["id"])
    assert root["s_clade"] == 1
    assert root["f_clade"] == 1
    assert child["s_own"] == 1
    assert child["f_own"] == 1


def test_save_load_preserves_state_and_erasure_invariant():
    arc, root, child = _seed()
    arc.record(root["id"], "coder", "t1", 1, 0, is_verifiable=True)
    arc.record(root["id"], "reviewer", "t1", 1, 0, is_verifiable=False)
    arc.record(child["id"], "reviewer", "t2", 0, 0, is_verifiable=False)

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "archive.json")
        arc.save(path)
        arc2 = Archive.load(path)

    assert len(arc2.nodes) == 2
    assert len(arc2.utility_records) == 3
    erased = arc2.selective_erase(role="reviewer", epoch=0)
    assert erased == 2
    stale = [r for r in arc2.utility_records
             if r["role"] == "reviewer" and r["epoch"] == 0]
    assert len(stale) == 0


def test_reviewer_cache_reuses_identical_solution_and_reviewer_scores():
    calls = {"count": 0}

    def fake_raw_call(prompt, system=None, thinking=llm.THINKING_EVAL):
        calls["count"] += 1
        return json.dumps({"score": 1, "rationale": "cached"})

    llm.reset_reviewer_cache()

    orig = llm._raw_call
    try:
        llm._raw_call = fake_raw_call
        agent = ReviewerAgent({"reviewer_fn": "", "coder_fn": ""})
        task = {"prompt": "def f(x):\n    return x", "task_id": "t"}
        assert agent.score("return x", task) == 1
        assert agent.score("return x", task) == 1
        assert calls["count"] == 1
    finally:
        llm._raw_call = orig


def test_epoch_boundary_promotes_better_reviewer_and_erasures_previous_epoch_records():
    arc = Archive()
    root = _new_node(
        coder_fn="def solve(task):\n    return 'return x'\n",
        reviewer_fn="def review(solution, task):\n    return 0\n",
    )
    arc.add_node(root)
    challenger = _new_node(
        parent_id=root["id"],
        coder_fn="def solve(task):\n    return 'return x'\n",
        reviewer_fn="def review(solution, task):\n    return 1\n",
    )
    arc.add_child(root["id"], challenger)

    task = {
        "task_id": "t1",
        "prompt": "def f(x):\n    return x",
        "test_code": "assert f(3) == 3",
    }

    solution = "return x"
    root_hash = llm._hash_text(root["reviewer_fn"])
    challenger_hash = llm._hash_text(challenger["reviewer_fn"])
    solution_hash = llm._hash_text(solution)

    arc.record(root["id"], "coder", "t1", 1, 0, is_verifiable=True,
               solution=solution, solution_hash=solution_hash,
               reviewer_fn_hash=root_hash)
    arc.record(challenger["id"], "coder", "t1", 1, 0, is_verifiable=True,
               solution=solution, solution_hash=solution_hash,
               reviewer_fn_hash=challenger_hash)

    arc.record(root["id"], "reviewer", "t1", 0, 0, is_verifiable=False,
               reviewer_output_cache="0", solution=solution,
               solution_hash=solution_hash, reviewer_fn_hash=root_hash)
    arc.record(challenger["id"], "reviewer", "t1", 0, 0, is_verifiable=False,
               reviewer_output_cache="0", solution=solution,
               solution_hash=solution_hash, reviewer_fn_hash=challenger_hash)

    run_epoch_boundary(arc, [task], 5)

    event = arc.epoch_events[-1]
    assert event["outcome"] == "promoted"
    assert event["winner_id"] == challenger["id"]
    stale = [
        rec
        for rec in arc.utility_records
        if rec["role"] == "reviewer" and rec["epoch"] == 0
    ]
    assert len(stale) == 0


def test_epoch_boundary_reads_cached_reviewer_scores():
    calls = {"count": 0}

    def fake_raw_call(prompt, system=None, thinking=llm.THINKING_EVAL):
        calls["count"] += 1
        return json.dumps({"score": 1, "rationale": "api"})

    arc = Archive()
    root = _new_node(
        coder_fn="def solve(task):\n    return 'return x'\n",
        reviewer_fn="",  # ensure local review function absent
    )
    challenger = _new_node(
        parent_id=root["id"],
        coder_fn="def solve(task):\n    return 'return x'\n",
        reviewer_fn="",  # ensure local review function absent
    )
    arc.add_node(root)
    arc.add_child(root["id"], challenger)

    task = {
        "task_id": "t1",
        "prompt": "def f(x):\n    return x",
        "test_code": "assert f(3) == 3",
    }
    solution = "return x"
    solution_hash = llm._hash_text(solution)
    reviewer_fn_hash = llm._hash_text("")

    arc.record(
        root["id"],
        "coder",
        "t1",
        1,
        0,
        is_verifiable=True,
        solution=solution,
        solution_hash=solution_hash,
        reviewer_fn_hash=reviewer_fn_hash,
    )
    arc.record(
        challenger["id"],
        "coder",
        "t1",
        1,
        0,
        is_verifiable=True,
        solution=solution,
        solution_hash=solution_hash,
        reviewer_fn_hash=reviewer_fn_hash,
    )
    arc.record(
        root["id"],
        "reviewer",
        "t1",
        1,
        0,
        is_verifiable=False,
        reviewer_output_cache="1",
        solution=solution,
        solution_hash=solution_hash,
        reviewer_fn_hash=reviewer_fn_hash,
    )
    arc.record(
        challenger["id"],
        "reviewer",
        "t1",
        1,
        0,
        is_verifiable=False,
        reviewer_output_cache="1",
        solution=solution,
        solution_hash=solution_hash,
        reviewer_fn_hash=reviewer_fn_hash,
    )

    llm.reset_reviewer_cache()
    llm.preload_reviewer_cache(arc.utility_records)

    orig = llm._raw_call
    try:
        llm._raw_call = fake_raw_call
        run_epoch_boundary(arc, [task], 5)
        assert calls["count"] == 0
        assert arc.epoch_events and arc.epoch_events[-1]["outcome"] == "retained"
        stats = llm.cache_reviewer_stats()
        assert stats["hits"] >= 1
    finally:
        llm._raw_call = orig


def test_no_challenger_boundary_records_event_without_erasure():
    arc = Archive()
    arc.add_node(_new_node(coder_fn="def solve(task):\n    return ''\n", reviewer_fn="def review(solution, task):\n    return 1\n"))

    task = {
        "task_id": "t1",
        "prompt": "def f(x):\n    return x",
        "test_code": "assert f(3) == 3",
    }

    run_epoch_boundary(arc, [task], step=3)

    assert arc.epoch_events == [
        {
            "step": 3,
            "outcome": "no_challenger",
            "incumbent_id": None,
            "winner_id": None,
            "gt_accuracy_before": 0.0,
            "gt_accuracy_after": 0.0,
            "records_erased": 0,
        }
    ]


def test_run_with_zero_checkpoint_records_no_challenger(tmp_path, monkeypatch):
    monkeypatch.setattr(search, "ARCHIVE_PATH", str(tmp_path / "archive.json"))
    monkeypatch.setattr(search, "RESULTS_PATH", str(tmp_path / "results.json"))

    result = search.run(mode="rqgm", budget=1, checkpoint=0, tasks_path="tasks/humaneval_20.json")

    assert result["epoch_events"] == [
        {
            "step": 0,
            "outcome": "no_challenger",
            "incumbent_id": None,
            "winner_id": None,
            "gt_accuracy_before": 0.0,
            "gt_accuracy_after": 0.0,
            "records_erased": 0,
        }
    ]
