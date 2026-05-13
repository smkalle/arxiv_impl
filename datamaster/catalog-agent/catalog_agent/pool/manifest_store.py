import json
from typing import Any
import redis.asyncio as aioredis

from .models import Manifest, ManifestMeta


class ManifestStore:
    """Redis HASH store for discovered data manifests."""

    def __init__(self, redis_client: aioredis.Redis, ttl_seconds: int = 30 * 86400):
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, manifest_id: str) -> str:
        return f"manifest:{manifest_id}"

    def _sku_source_key(self, sku_id: str, source: str) -> str:
        return f"mss:{sku_id}:{source}"

    async def add(self, manifest: Manifest) -> str:
        key = self._key(manifest.meta.manifest_id)
        data = manifest.model_dump_json()
        await self._redis.set(key, data, ex=self._ttl)
        # secondary index for exists_for_sku_source
        idx_key = self._sku_source_key(manifest.meta.sku_id, manifest.meta.source)
        await self._redis.set(idx_key, manifest.meta.manifest_id, ex=self._ttl)
        return manifest.meta.manifest_id

    async def get(self, manifest_id: str) -> Manifest | None:
        raw = await self._redis.get(self._key(manifest_id))
        if raw is None:
            return None
        return Manifest.model_validate_json(raw)

    async def get_candidates(
        self,
        sku_id: str | None = None,
        category: str | None = None,
        min_delta: float | None = None,
        committed: bool | None = None,
    ) -> list[Manifest]:
        manifests: list[Manifest] = []
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match="manifest:*", count=200)
            for key in keys:
                raw = await self._redis.get(key)
                if raw is None:
                    continue
                m = Manifest.model_validate_json(raw)
                if sku_id and m.meta.sku_id != sku_id:
                    continue
                if min_delta is not None and (m.meta.score_delta is None or m.meta.score_delta < min_delta):
                    continue
                if committed is not None and m.meta.committed != committed:
                    continue
                manifests.append(m)
            if cursor == 0:
                break
        return manifests

    async def mark_committed(self, manifest_id: str) -> None:
        m = await self.get(manifest_id)
        if m is None:
            return
        m.meta.committed = True
        await self._redis.set(self._key(manifest_id), m.model_dump_json(), ex=self._ttl)

    async def update_score_delta(self, manifest_id: str, delta: float) -> None:
        m = await self.get(manifest_id)
        if m is None:
            return
        m.meta.score_delta = delta
        await self._redis.set(self._key(manifest_id), m.model_dump_json(), ex=self._ttl)

    async def exists_for_sku_source(self, sku_id: str, source: str) -> bool:
        idx_key = self._sku_source_key(sku_id, source)
        return await self._redis.exists(idx_key) > 0

    async def store_rollback_snapshot(self, sku_id: str, snapshot: dict) -> None:
        key = f"rollback:{sku_id}"
        await self._redis.set(key, json.dumps(snapshot), ex=self._ttl)

    async def get_rollback_snapshot(self, sku_id: str) -> dict | None:
        raw = await self._redis.get(f"rollback:{sku_id}")
        if raw is None:
            return None
        return json.loads(raw)
