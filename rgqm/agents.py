import json

from archive import _new_node
from llm import (
    call,
    THINKING_EVAL,
    THINKING_META,
    cache_reviewer_key,
    _hash_text,
)


def _compile_fn(code_text, fn_name):
    ns = {}
    try:
        compiled = compile((code_text or "").strip(), "node.py", "exec")
        exec(compiled, ns)
        fn = ns.get(fn_name)
        if callable(fn):
            return fn
    except Exception:
        return None
    return None


def _normalize_binary(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"1", "true", "pass", "passed", "yes", "y"}:
            return 1
        if s in {"0", "false", "fail", "failed", "no", "n"}:
            return 0
        try:
            return 1 if int(float(s)) == 1 else 0
        except Exception:
            pass
    return 0


class CoderAgent:
    def __init__(self, node):
        self.node = node

    def solve(self, task):
        fn = _compile_fn(self.node.get("coder_fn", ""), "solve")
        if fn is not None:
            try:
                out = fn(task)
                if isinstance(out, str):
                    return out.strip()
            except Exception:
                pass
        prompt = (
            "You are the coder. Complete this HumanEval task. "
            "Return only the Python function body.\n"
            f"Task:\n{task['prompt']}\n"
        )
        return call(prompt, thinking=THINKING_EVAL)


class ReviewerAgent:
    def __init__(self, node):
        self.node = node

    def score(self, solution, task):
        fn = _compile_fn(self.node.get("reviewer_fn", ""), "review")
        if fn is not None:
            try:
                return _normalize_binary(fn((solution or ""), task))
            except Exception:
                pass

        solution_hash = _hash_text(solution)
        reviewer_fn_hash = _hash_text(self.node.get("reviewer_fn", ""))
        cache_key = cache_reviewer_key(solution_hash, reviewer_fn_hash)
        prompt = (
            "You are the reviewer. Score the solution 0 (fail) or 1 (pass). "
            "Return JSON {\"score\": 0|1}.\n"
            f"Task:\n{task['prompt']}\nSolution:\n{solution}\n"
        )
        resp = call(prompt, thinking=THINKING_EVAL, cache_key=cache_key)
        try:
            parsed = json.loads(resp)
            return _normalize_binary(parsed.get("score", 0))
        except Exception:
            return _normalize_binary(resp)


class MetaAgent:
    def expand(self, parent, ancestor_logs=None):
        prompt = (
            "meta-agent: propose an improved coder_fn and reviewer_fn for the "
            "next archive node. Return JSON {\"coder_fn\": str, \"reviewer_fn\": str}."
        )
        resp = call(prompt, system="You are the meta-agent.", thinking=THINKING_META)
        try:
            data = json.loads(resp)
        except Exception:
            data = {}
        child = _new_node(
            parent_id=parent["id"],
            coder_fn=data.get("coder_fn", parent.get("coder_fn", "")),
            reviewer_fn=data.get("reviewer_fn", parent.get("reviewer_fn", "")),
        )
        return child
