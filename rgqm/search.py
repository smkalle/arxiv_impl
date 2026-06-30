import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile

from archive import Archive, _new_node, eps_best_belief
from agents import CoderAgent, ReviewerAgent, MetaAgent
import llm

BUDGET = 80
CHECKPOINT = 30
ALPHA = 0.6
ARCHIVE_PATH = "archive.json"
RESULTS_PATH = "results.json"


def _assert_erasure_invariant(archive):
    stale = [
        rec for rec in archive.utility_records
        if rec["role"] == "reviewer" and rec["epoch"] == 0
    ]
    assert len(stale) == 0, "erasure invariant violated"


def load_tasks(path="tasks/humaneval_20.json"):
    with open(path) as f:
        return json.load(f)


def least_evaluated_task(node, role, tasks, archive):
    counts = {t["task_id"]: 0 for t in tasks}
    for r in archive.utility_records:
        if r["node_id"] == node["id"] and r["role"] == role:
            counts[r["task_id"]] = counts.get(r["task_id"], 0) + 1
    return sorted(tasks, key=lambda t: counts[t["task_id"]])[0]


def _extract_def_signature(task_prompt):
    if not task_prompt:
        return None
    m = re.search(
        r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*(?:->\s*[^:]+)?:",
        task_prompt,
        re.M,
    )
    if not m:
        return None
    name, args = m.group(1), m.group(2)
    return f"def {name}({args}):"


def _wrap_solution_as_function(solution, task_prompt):
    source = (solution or "").rstrip()
    if not source:
        return source
    if re.match(r"^\s*def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", source):
        return source
    signature = _extract_def_signature(task_prompt)
    if signature is None:
        return source
    lines = source.splitlines() or [""]
    indented = []
    for ln in lines:
        if not ln.strip():
            indented.append("    ")
        elif ln.startswith("    "):
            indented.append(ln)
        else:
            indented.append("    " + ln)
    return signature + "\n" + "\n".join(indented)


def run_tests(solution, task):
    code = _wrap_solution_as_function(solution, task.get("prompt", ""))
    code = code + "\n\n" + task.get("test_code", "") + "\n"
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code)
            path = f.name
        r = subprocess.run([sys.executable, path], capture_output=True, timeout=10)
        return 1 if r.returncode == 0 else 0
    except Exception:
        return 0
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except Exception:
                pass


def _solution_record(archive, node_id, task_id):
    for rec in reversed(archive.utility_records):
        if (
            rec["node_id"] == node_id
            and rec["role"] == "coder"
            and rec.get("task_id") == task_id
            and rec.get("solution") is not None
        ):
            return rec
    return None


def evaluate(node, role, task, epoch, archive):
    solution = CoderAgent(node).solve(task)
    if role == "coder":
        outcome = run_tests(solution, task)
        archive.record(
            node["id"],
            "coder",
            task["task_id"],
            outcome,
            epoch,
            is_verifiable=True,
            reviewer_output_cache=None,
            solution=solution,
            solution_hash=llm._hash_text(solution),
            reviewer_fn_hash=llm._hash_text(node.get("reviewer_fn", "")),
        )
        return

    if role != "reviewer":
        return

    score = ReviewerAgent(node).score(solution, task)
    archive.record(
        node["id"],
        "reviewer",
        task["task_id"],
        score,
        epoch,
        is_verifiable=False,
        reviewer_output_cache=str(score),
        solution=solution,
        solution_hash=llm._hash_text(solution),
        reviewer_fn_hash=llm._hash_text(node.get("reviewer_fn", "")),
    )


def build_held_out(tasks, size=50, seed=7):
    if not tasks:
        return []
    if len(tasks) <= size:
        return list(tasks)
    rng = random.Random(seed)
    return rng.sample(list(tasks), size)


def _reviewer_scores_on_held_out(node, held_out_tasks, archive):
    reviewer = ReviewerAgent(node)
    coder = CoderAgent(node)
    successes = 0
    failures = 0
    for task in held_out_tasks:
        task_id = task["task_id"]
        rec = _solution_record(archive, node["id"], task_id)
        solution = rec.get("solution") if rec else None
        if solution is None:
            solution = coder.solve(task)
            if solution is None:
                solution = ""
        gt = run_tests(solution, task)
        pred = reviewer.score(solution, task)
        if int(pred) == int(gt):
            successes += 1
        else:
            failures += 1
    return successes, failures


def run_epoch_boundary(archive, held_out_tasks, step):
    if len(archive.nodes) < 2:
        archive.log_epoch_event({
            "step": step,
            "outcome": "no_challenger",
            "incumbent_id": None,
            "winner_id": None,
            "gt_accuracy_before": 0.0,
            "gt_accuracy_after": 0.0,
            "records_erased": 0,
        })
        return

    incumbent = archive.nodes[0]
    scores = {}
    for node in archive.nodes:
        successes, failures = _reviewer_scores_on_held_out(node, held_out_tasks, archive)
        if successes == 0 and failures == 0:
            # Keep the prior broad enough to avoid hard bias on empty data.
            successes = 1
            failures = 1
        scores[node["id"]] = (successes, failures)

    incumbent_id = incumbent["id"]
    incumbent_score = eps_best_belief(*scores[incumbent_id])
    winner_id = incumbent_id
    winner_score = incumbent_score
    for node_id, vals in scores.items():
        if node_id == incumbent_id:
            continue
        candidate = eps_best_belief(*vals)
        if candidate > winner_score:
            winner_id = node_id
            winner_score = candidate

    before = incumbent_score
    after = eps_best_belief(*scores[winner_id])

    if winner_id == incumbent_id:
        archive.log_epoch_event({
            "step": step,
            "outcome": "retained",
            "incumbent_id": incumbent_id,
            "winner_id": incumbent_id,
            "gt_accuracy_before": before,
            "gt_accuracy_after": after,
            "records_erased": 0,
        })
        return

    erased = archive.selective_erase(role="reviewer", epoch=0)
    _assert_erasure_invariant(archive)
    archive.log_epoch_event({
        "step": step,
        "outcome": "promoted",
        "incumbent_id": incumbent_id,
        "winner_id": winner_id,
        "gt_accuracy_before": before,
        "gt_accuracy_after": after,
        "records_erased": erased,
    })


def run(mode="rqgm", budget=BUDGET, checkpoint=CHECKPOINT, tasks_path="tasks/humaneval_20.json"):
    llm.reset_token_log()
    llm.reset_reviewer_cache()

    tasks = load_tasks(tasks_path)
    held_out = build_held_out(tasks)

    archive = Archive()
    seed = _new_node(
        coder_fn="def solve(task):\n    return ''\n",
        reviewer_fn="def review(solution, task):\n    return 1\n",
    )
    archive.add_node(seed)
    llm.preload_reviewer_cache(archive.utility_records)

    epoch = 0
    boundary_fired = False

    for step in range(budget):
        if mode == "rqgm" and step == checkpoint and not boundary_fired:
            run_epoch_boundary(archive, held_out, step)
            boundary_fired = True
            if archive.epoch_events and archive.epoch_events[-1].get("outcome") == "promoted":
                _assert_erasure_invariant(archive)
            epoch = 1

        if step ** ALPHA >= len(archive.nodes) and step < budget - 1:
            parent = archive.nodes[-1]
            child = MetaAgent().expand(parent)
            archive.add_child(parent["id"], child)
            archive.save(ARCHIVE_PATH)
            continue

        node = archive.nodes[step % len(archive.nodes)]
        role = "coder" if step % 2 == 0 else "reviewer"
        task = least_evaluated_task(node, role, tasks, archive)
        evaluate(node, role, task, epoch, archive)
        archive.save(ARCHIVE_PATH)

    best = archive.best_belief_agent()
    result = {
        "mode": mode,
        "budget": budget,
        "checkpoint": checkpoint,
        "nodes": len(archive.nodes),
        "utility_records": len(archive.utility_records),
        "epoch_events": archive.epoch_events,
        "blended_tokens": llm.blended_tokens(),
        "blended_cost_usd": round(llm.blended_cost_usd(), 6),
        "best_node_id": best["id"] if best else None,
        "reviewer_cache": llm.cache_reviewer_stats(),
    }
    archive.save(ARCHIVE_PATH)
    with open(RESULTS_PATH, "w") as f:
        json.dump(result, f, indent=2)
    return result


def main():
    p = argparse.ArgumentParser(description="EpochForge Lite — RQGM scaffold")
    p.add_argument("--mode", default="rqgm", choices=["rqgm", "hgm_h"])
    p.add_argument("--budget", type=int, default=BUDGET)
    p.add_argument("--checkpoint", type=int, default=CHECKPOINT)
    p.add_argument("--tasks", default="tasks/humaneval_20.json")
    args = p.parse_args()

    checkpoint = -1 if args.mode == "hgm_h" else args.checkpoint
    res = run(args.mode, args.budget, checkpoint, args.tasks)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
