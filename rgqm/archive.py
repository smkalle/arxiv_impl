import json
import os
import tempfile
import hashlib
import uuid

from scipy.stats import beta as beta_dist

EPSILON = 0.05


def _new_node(parent_id=None, coder_fn="", reviewer_fn=""):
    return {
        "id": str(uuid.uuid4()),
        "parent_id": parent_id,
        "coder_fn": coder_fn,
        "reviewer_fn": reviewer_fn,
        "s_own": 0,
        "f_own": 0,
        "s_clade": 0,
        "f_clade": 0,
        "best_belief": 0.0,
        "children": [],
    }


def _hash_text(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def eps_best_belief(successes, failures, epsilon=EPSILON):
    if successes + failures == 0:
        return 0.0
    return float(beta_dist.ppf(epsilon, successes + 1, failures + 1))


class Archive:
    def __init__(self):
        self.nodes = []
        self.utility_records = []
        self.epoch_events = []
        self._index = {}

    def add_node(self, node):
        self.nodes.append(node)
        self._index[node["id"]] = node
        if node["parent_id"] in self._index:
            self._index[node["parent_id"]]["children"].append(node["id"])
        return node

    def add_child(self, parent_id, child):
        child["parent_id"] = parent_id
        return self.add_node(child)

    def get(self, node_id):
        return self._index.get(node_id)

    def _descendants(self, node_id):
        out = []
        stack = [node_id]
        while stack:
            nid = stack.pop()
            node = self.get(nid)
            if node is None:
                continue
            out.append(nid)
            stack.extend(node["children"])
        return out

    def recompute_clade_aggregates(self):
        for node in self.nodes:
            clade = set(self._descendants(node["id"]))
            s = sum(r["outcome"] for r in self.utility_records
                    if r["node_id"] in clade and r["role"] == "coder")
            f = sum(1 for r in self.utility_records
                    if r["node_id"] in clade and r["role"] == "coder" and r["outcome"] == 0)
            node["s_clade"] = s
            node["f_clade"] = f

    def _recompute_own(self):
        for node in self.nodes:
            node["s_own"] = 0
            node["f_own"] = 0
        for r in self.utility_records:
            node = self.get(r["node_id"])
            if node is None:
                continue
            if r["outcome"] == 1:
                node["s_own"] += 1
            else:
                node["f_own"] += 1
        for node in self.nodes:
            node["best_belief"] = eps_best_belief(node["s_own"], node["f_own"])

    def record(self, node_id, role, task_id, outcome, epoch, is_verifiable,
               reviewer_output_cache=None, solution=None,
               solution_hash=None, reviewer_fn_hash=None):
        rec = {
            "id": str(uuid.uuid4()),
            "node_id": node_id,
            "role": role,
            "task_id": task_id,
            "outcome": int(outcome),
            "epoch": epoch,
            "is_verifiable": bool(is_verifiable),
            "reviewer_output_cache": reviewer_output_cache,
            "solution_hash": solution_hash or _hash_text(solution or ""),
            "reviewer_fn_hash": reviewer_fn_hash or None,
            "solution": solution,
        }
        self.utility_records.append(rec)
        self._recompute_own()
        self.recompute_clade_aggregates()
        return rec

    def selective_erase(self, role="reviewer", epoch=0):
        survivors = []
        erased = 0
        for r in self.utility_records:
            if r["role"] == role and r["epoch"] == epoch:
                if r["is_verifiable"]:
                    raise AssertionError("refused to erase verifiable (coder) record")
                erased += 1
                continue
            survivors.append(r)
        self.utility_records = survivors
        self._recompute_own()
        self.recompute_clade_aggregates()
        # Protocol invariant enforced at source of truth.
        stale = [
            rec
            for rec in self.utility_records
            if rec["role"] == "reviewer" and rec["epoch"] == 0
        ]
        assert len(stale) == 0, "erasure invariant violated"
        return erased

    def log_epoch_event(self, event):
        self.epoch_events.append(event)

    def best_belief_agent(self, epsilon=EPSILON):
        best = None
        for node in self.nodes:
            if best is None or node["best_belief"] > best["best_belief"]:
                best = node
        return best

    def to_dict(self):
        return {
            "nodes": self.nodes,
            "utility_records": self.utility_records,
            "epoch_events": self.epoch_events,
        }

    def save(self, path):
        d = self.to_dict()
        dirpath = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmp = tempfile.mkstemp(dir=dirpath, prefix=".archive_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(d, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    @classmethod
    def load(cls, path):
        with open(path) as f:
            d = json.load(f)
        arc = cls()
        arc.nodes = d.get("nodes", [])
        arc.utility_records = d.get("utility_records", [])
        arc.epoch_events = d.get("epoch_events", [])
        arc._index = {n["id"]: n for n in arc.nodes}
        return arc
