import json
from abc import ABC, abstractmethod

import httpx

from catalog_agent.api.models import EnrichRequest


class BaseSKUStore(ABC):
    @abstractmethod
    async def get(self, sku_id: str) -> dict | None: ...

    @abstractmethod
    async def get_batch(self, request: EnrichRequest) -> list[dict]: ...

    @abstractmethod
    async def update(self, sku_id: str, attributes: dict) -> None: ...

    @abstractmethod
    async def store_rollback_snapshot(self, sku_id: str, snapshot: dict) -> None: ...

    @abstractmethod
    async def get_rollback_snapshot(self, sku_id: str) -> dict | None: ...


class SKUStore(BaseSKUStore):
    """Live catalog API client."""

    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def get(self, sku_id: str) -> dict | None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self._base_url}/skus/{sku_id}", headers=self._headers())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def get_batch(self, request: EnrichRequest) -> list[dict]:
        params: dict = {}
        if request.sku_ids:
            params["ids"] = ",".join(request.sku_ids)
        if request.categories:
            params["categories"] = ",".join(request.categories)
        if request.quality_filter:
            params.update(request.quality_filter)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self._base_url}/skus", params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json()["skus"]

    async def update(self, sku_id: str, attributes: dict) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                f"{self._base_url}/skus/{sku_id}",
                json={"attributes": attributes},
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def store_rollback_snapshot(self, sku_id: str, snapshot: dict) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self._base_url}/skus/{sku_id}/snapshots",
                json=snapshot,
                headers=self._headers(),
            )

    async def get_rollback_snapshot(self, sku_id: str) -> dict | None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base_url}/skus/{sku_id}/snapshots/latest",
                headers=self._headers(),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()


class MockSKUStore(BaseSKUStore):
    """In-memory SKU store for tests and local dev."""

    def __init__(self):
        self._skus: dict[str, dict] = {}
        self._snapshots: dict[str, dict] = {}

    def seed(self, skus: list[dict]) -> None:
        for sku in skus:
            self._skus[sku["sku_id"]] = sku

    async def get(self, sku_id: str) -> dict | None:
        return self._skus.get(sku_id)

    async def get_batch(self, request: EnrichRequest) -> list[dict]:
        skus = list(self._skus.values())
        if request.sku_ids:
            skus = [s for s in skus if s["sku_id"] in request.sku_ids]
        if request.categories:
            skus = [s for s in skus if s.get("category_l2") in request.categories]
        if request.quality_filter and "max_score" in request.quality_filter:
            max_s = request.quality_filter["max_score"]
            skus = [s for s in skus if len(s.get("attributes", {})) * 1.5 <= max_s]
        return skus

    async def update(self, sku_id: str, attributes: dict) -> None:
        if sku_id in self._skus:
            self._skus[sku_id]["attributes"] = attributes

    async def store_rollback_snapshot(self, sku_id: str, snapshot: dict) -> None:
        self._snapshots[sku_id] = snapshot

    async def get_rollback_snapshot(self, sku_id: str) -> dict | None:
        return self._snapshots.get(sku_id)
