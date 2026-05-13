import httpx
from abc import ABC, abstractmethod


class BaseCatalogLabScorer(ABC):
    @abstractmethod
    async def score(self, sku: dict) -> float: ...

    @abstractmethod
    async def score_batch(self, skus: list[dict]) -> list[float]: ...

    async def score_delta(self, baseline_sku: dict, candidate_sku: dict) -> float:
        baseline, candidate = await self.score_batch([baseline_sku, candidate_sku])
        return candidate - baseline


class CatalogLabScorer(BaseCatalogLabScorer):
    """Live CatalogLab HTTP scorer."""

    def __init__(self, base_url: str, api_key: str, batch_size: int = 50):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._batch_size = batch_size

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    async def score(self, sku: dict) -> float:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base_url}/score",
                json=sku,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return float(resp.json()["score"])

    async def score_batch(self, skus: list[dict]) -> list[float]:
        results: list[float] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for i in range(0, len(skus), self._batch_size):
                batch = skus[i:i + self._batch_size]
                resp = await client.post(
                    f"{self._base_url}/score/batch",
                    json={"skus": batch},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                results.extend(resp.json()["scores"])
        return results


class MockCatalogLabScorer(BaseCatalogLabScorer):
    """
    Deterministic mock scorer. Score = number of non-null attributes * 1.5, capped at 100.
    Used when CATALOGLAB_URL is unset or in tests.
    """

    def _compute_score(self, sku: dict) -> float:
        attrs = sku.get("attributes", sku)
        filled = sum(
            1 for v in attrs.values()
            if v is not None and v != "" and v != [] and not str(v).startswith("_")
        )
        return min(filled * 1.5, 100.0)

    async def score(self, sku: dict) -> float:
        return self._compute_score(sku)

    async def score_batch(self, skus: list[dict]) -> list[float]:
        return [self._compute_score(s) for s in skus]
