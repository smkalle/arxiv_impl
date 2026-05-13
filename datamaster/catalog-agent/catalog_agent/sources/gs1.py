import httpx
from .base import SourceAdapter


class GS1Adapter(SourceAdapter):
    source_name = "gs1"

    def __init__(self, api_url: str, api_key: str):
        self._api_url = api_url
        self._api_key = api_key

    async def fetch(self, sku: dict) -> dict | None:
        gtin = sku.get("gtin") or sku.get("jan") or sku.get("ean")
        if not gtin:
            return None
        headers = {"X-API-Key": self._api_key} if self._api_key else {}
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    self._api_url,
                    params={"gtin": gtin, "lang": "en"},
                    headers=headers,
                )
            except httpx.RequestError:
                return None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        return resp.json()

    def source_url(self, sku: dict) -> str:
        gtin = sku.get("gtin", "")
        return f"{self._api_url}?gtin={gtin}&lang=en"
