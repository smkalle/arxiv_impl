import httpx
from .base import SourceAdapter

FOOD_CATEGORIES = {
    "beverages", "food", "snacks", "dairy", "health", "nutrition",
    "confectionery", "bakery", "condiments", "canned_goods",
}


class OpenFoodFactsAdapter(SourceAdapter):
    source_name = "open_food_facts"

    def __init__(self, base_url: str = "https://world.openfoodfacts.org/api/v2"):
        self._base_url = base_url.rstrip("/")

    async def fetch(self, sku: dict) -> dict | None:
        category = (sku.get("category_l2") or "").lower()
        if category not in FOOD_CATEGORIES:
            return None
        gtin = sku.get("gtin") or sku.get("jan") or sku.get("ean")
        if not gtin:
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/product/{gtin}.json",
                    headers={"User-Agent": "CatalogAgent/0.1 (data enrichment)"},
                )
            except httpx.RequestError:
                return None
        if resp.status_code != 200:
            return None
        body = resp.json()
        if body.get("status") == 0:
            return None
        return body.get("product") or None

    def source_url(self, sku: dict) -> str:
        gtin = sku.get("gtin", "")
        return f"{self._base_url}/product/{gtin}.json"
