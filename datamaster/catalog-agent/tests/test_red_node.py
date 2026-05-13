import pytest
import respx
import httpx

from catalog_agent.sources.gs1 import GS1Adapter
from catalog_agent.sources.open_food_facts import OpenFoodFactsAdapter
from catalog_agent.agent.red_node import run_red_node
from catalog_agent.pool.models import Manifest


GS1_RESPONSE = {
    "brandName": "TestBrand",
    "netContent": "500",
    "netContentUom": "ml",
    "countryOfOrigin": "JP",
    "gpcCategoryCode": "10000248",
    "productDescription": "Green tea 500ml",
}

OFF_RESPONSE = {
    "status": 1,
    "product": {
        "product_name": "TestBrand Green Tea",
        "brands": "TestBrand",
        "quantity": "500ml",
        "ingredients_text": "water, green tea extract",
        "allergens": "",
        "nutriments": {"energy-kcal_100g": 1},
        "packaging": "PET bottle",
        "countries": "Japan",
        "labels": "organic",
    },
}


@respx.mock
async def test_gs1_fetch_success(sample_sku):
    respx.get("https://gepir.gs1.org/index.php/search-by-gtin").mock(
        return_value=httpx.Response(200, json=GS1_RESPONSE)
    )
    adapter = GS1Adapter(
        api_url="https://gepir.gs1.org/index.php/search-by-gtin",
        api_key="test-key",
    )
    result = await adapter.fetch(sample_sku)
    assert result is not None
    assert result["brandName"] == "TestBrand"


@respx.mock
async def test_gs1_fetch_404_returns_none(sample_sku):
    respx.get("https://gepir.gs1.org/index.php/search-by-gtin").mock(
        return_value=httpx.Response(404)
    )
    adapter = GS1Adapter(
        api_url="https://gepir.gs1.org/index.php/search-by-gtin",
        api_key="test-key",
    )
    result = await adapter.fetch(sample_sku)
    assert result is None


@respx.mock
async def test_off_fetch_success(sample_sku):
    respx.get("https://world.openfoodfacts.org/api/v2/product/4901234567890.json").mock(
        return_value=httpx.Response(200, json=OFF_RESPONSE)
    )
    adapter = OpenFoodFactsAdapter()
    result = await adapter.fetch(sample_sku)
    assert result is not None
    assert result["brands"] == "TestBrand"


@respx.mock
async def test_off_skips_non_food_category(sample_sku):
    sample_sku["category_l2"] = "electronics"
    adapter = OpenFoodFactsAdapter()
    result = await adapter.fetch(sample_sku)
    assert result is None


@respx.mock
async def test_off_fetch_product_not_found(sample_sku):
    respx.get("https://world.openfoodfacts.org/api/v2/product/4901234567890.json").mock(
        return_value=httpx.Response(200, json={"status": 0})
    )
    adapter = OpenFoodFactsAdapter()
    result = await adapter.fetch(sample_sku)
    assert result is None


@respx.mock
async def test_gs1_no_gtin_returns_none():
    adapter = GS1Adapter(
        api_url="https://gepir.gs1.org/index.php/search-by-gtin",
        api_key="",
    )
    result = await adapter.fetch({"sku_id": "x", "category_l2": "beverages"})
    assert result is None


@respx.mock
async def test_run_red_node_writes_manifests(manifest_store, memory_store, sample_sku):
    respx.get("https://gepir.gs1.org/index.php/search-by-gtin").mock(
        return_value=httpx.Response(200, json=GS1_RESPONSE)
    )
    respx.get("https://world.openfoodfacts.org/api/v2/product/4901234567890.json").mock(
        return_value=httpx.Response(200, json=OFF_RESPONSE)
    )

    from catalog_agent.sources.gs1 import GS1Adapter
    from catalog_agent.sources.open_food_facts import OpenFoodFactsAdapter

    sources = [
        GS1Adapter("https://gepir.gs1.org/index.php/search-by-gtin", ""),
        OpenFoodFactsAdapter(),
    ]
    manifest_ids = await run_red_node(
        node_id="r1",
        sku_batch=[sample_sku],
        sources=sources,
        pool=manifest_store,
        memory=memory_store,
    )
    assert len(manifest_ids) == 2
    for mid in manifest_ids:
        m = await manifest_store.get(mid)
        assert m is not None
        assert m.meta.sku_id == "RAK-TEST-001"
