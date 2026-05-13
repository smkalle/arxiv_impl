import json
import re
import httpx
from .base import SourceAdapter


class SchemaOrgAdapter(SourceAdapter):
    source_name = "schema_org"

    async def fetch(self, sku: dict) -> dict | None:
        brand = sku.get("brand", "")
        title = sku.get("title", "")
        if not brand or not title:
            return None
        # Without a real brand URL registry, skip in production; mock returns data in tests.
        return None

    async def fetch_from_url(self, url: str) -> dict | None:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            try:
                resp = await client.get(url, headers={"User-Agent": "CatalogAgent/0.1"})
            except httpx.RequestError:
                return None
        if resp.status_code != 200:
            return None
        return self._extract_product_jsonld(resp.text)

    def _extract_product_jsonld(self, html: str) -> dict | None:
        for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
            elif isinstance(data, dict) and data.get("@type") == "Product":
                return data
        return None

    def source_url(self, sku: dict) -> str:
        return f"schema_org://{sku.get('brand', 'unknown')}/{sku.get('sku_id', '')}"
