import math
import uuid
from typing import Literal
import networkx as nx


class UCBScheduler:
    """DataTree using NetworkX DiGraph with UCB-1 node selection."""

    def __init__(self, exploration_c: float = 1.0):
        self.G: nx.DiGraph = nx.DiGraph()
        self.root_id = "root"
        self.G.add_node(self.root_id, type="root", visits=0, reward=0.0)
        self.exploration_c = exploration_c
        self._total_iterations = 0

    def add_node(self, parent_id: str, node_type: Literal["red", "black"]) -> str:
        node_id = f"{node_type}_{uuid.uuid4().hex[:6]}"
        self.G.add_node(node_id, type=node_type, visits=0, reward=0.0)
        self.G.add_edge(parent_id, node_id)
        return node_id

    def get_frontier(self) -> list[str]:
        """Return leaf nodes (nodes with no children) that are not the root."""
        return [
            n for n in self.G.nodes
            if n != self.root_id and self.G.out_degree(n) == 0
        ]

    def _ucb_score(self, node_id: str) -> float:
        data = self.G.nodes[node_id]
        visits = data["visits"]
        if visits == 0:
            return float("inf")
        exploit = data["reward"] / visits
        explore = self.exploration_c * math.sqrt(
            math.log(max(self._total_iterations, 1)) / visits
        )
        return exploit + explore

    def select_node(self, iteration: int) -> str:
        self._total_iterations = max(self._total_iterations, iteration + 1)
        frontier = self.get_frontier()
        if not frontier:
            return self.root_id
        return max(frontier, key=self._ucb_score)

    def backpropagate(self, node_id: str, reward: float) -> None:
        """Walk from node to root, incrementing visits and reward."""
        current = node_id
        while current is not None:
            data = self.G.nodes[current]
            data["visits"] += 1
            data["reward"] += reward
            parents = list(self.G.predecessors(current))
            current = parents[0] if parents else None

    def node_stats(self) -> list[dict]:
        return [
            {
                "node_id": n,
                "type": self.G.nodes[n]["type"],
                "visits": self.G.nodes[n]["visits"],
                "reward": round(self.G.nodes[n]["reward"], 3),
                "ucb": round(self._ucb_score(n), 3) if n != self.root_id else None,
            }
            for n in self.G.nodes
        ]
