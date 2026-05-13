import json
from datetime import datetime, timezone
import redis.asyncio as aioredis


class CategoryInsightStore:
    """
    Append-only log of enrichment outcomes keyed by (category_l2, source).
    Uses Redis sorted sets for source ranking + JSON append log for fill rates.
    """

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client

    def _delta_key(self, category: str) -> str:
        return f"insights:delta:{category}"

    def _fill_key(self, category: str, source: str) -> str:
        return f"insights:fill:{category}:{source}"

    def _log_key(self, category: str) -> str:
        return f"insights:log:{category}"

    async def record_outcome(
        self,
        category_l2: str,
        source: str,
        score_delta: float,
        attributes_filled: list[str],
        committed: bool,
    ) -> None:
        # Update running avg delta in sorted set (score = cumulative, member = source)
        delta_key = self._delta_key(category_l2)
        await self._redis.zincrby(delta_key, score_delta, source)

        # Track fill counts per attribute per (category, source)
        fill_key = self._fill_key(category_l2, source)
        for attr in attributes_filled:
            await self._redis.hincrby(fill_key, attr, 1)

        # Append to log
        log_entry = {
            "source": source,
            "score_delta": score_delta,
            "attributes_filled": attributes_filled,
            "committed": committed,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        await self._redis.rpush(self._log_key(category_l2), json.dumps(log_entry))

    async def get_top_sources(self, category_l2: str, top_n: int = 3) -> list[str]:
        delta_key = self._delta_key(category_l2)
        results = await self._redis.zrevrange(delta_key, 0, top_n - 1)
        if not results:
            return ["open_food_facts", "gs1", "schema_org"][:top_n]
        return [r.decode() if isinstance(r, bytes) else r for r in results]

    async def get_fill_rates(self, category_l2: str) -> dict[str, float]:
        """Return {attribute: count} for this category across all sources."""
        pattern = self._fill_key(category_l2, "*")
        cursor = 0
        combined: dict[str, int] = {}
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            for key in keys:
                data = await self._redis.hgetall(key)
                for attr, count in data.items():
                    attr_s = attr.decode() if isinstance(attr, bytes) else attr
                    combined[attr_s] = combined.get(attr_s, 0) + int(count)
            if cursor == 0:
                break
        return {k: float(v) for k, v in combined.items()}

    async def get_recent_outcomes(self, category_l2: str, limit: int = 50) -> list[dict]:
        raw = await self._redis.lrange(self._log_key(category_l2), -limit, -1)
        return [json.loads(r) for r in raw]
