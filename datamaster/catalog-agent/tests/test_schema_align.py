from catalog_agent.merge.schema_align import SchemaAligner

aligner = SchemaAligner()


def test_align_open_food_facts():
    raw = {
        "product_name": "Green Tea 500ml",
        "brands": "TestBrand",
        "quantity": "500ml",
        "ingredients_text": "water, green tea",
        "allergens": "",
        "nutriments": {"energy-kcal_100g": 2},
        "packaging": "PET bottle",
        "countries": "Japan",
        "labels": "organic",
    }
    aligned = aligner.align("open_food_facts", raw)
    assert aligned["title"] == "Green Tea 500ml"
    assert aligned["brand"] == "TestBrand"
    assert aligned["net_content"] == "500ml"
    assert aligned["ingredients"] == "water, green tea"
    assert aligned["packaging_type"] == "PET bottle"
    assert aligned["country_of_origin"] == "Japan"
    assert aligned["certifications"] == "organic"
    assert "nutrition.energy_kcal" in aligned


def test_align_gs1():
    raw = {
        "brandName": "TestBrand",
        "netContent": "500",
        "netContentUom": "ml",
        "countryOfOrigin": "JP",
        "gpcCategoryCode": "10000248",
        "productDescription": "Green tea 500ml",
    }
    aligned = aligner.align("gs1", raw)
    assert aligned["brand"] == "TestBrand"
    assert aligned["net_content"] == "500"
    assert aligned["net_content_uom"] == "ml"
    assert aligned["country_of_origin"] == "JP"
    assert aligned["description"] == "Green tea 500ml"


def test_align_schema_org():
    raw = {
        "name": "Green Tea",
        "brand": {"name": "TestBrand"},
        "color": "green",
        "size": "500ml",
        "material": None,
        "description": "Premium green tea",
        "mpn": "GT-500",
    }
    aligned = aligner.align("schema_org", raw)
    assert aligned["title"] == "Green Tea"
    assert aligned.get("color") == "green"
    assert aligned.get("size") == "500ml"
    assert aligned.get("mpn") == "GT-500"
    assert "material" not in aligned


def test_unknown_fields_go_to_unmapped():
    raw = {"brandName": "X", "weirdField": "val"}
    aligned = aligner.align("gs1", raw)
    assert "weirdField" in aligned.get("_unmapped", {})


def test_empty_string_values_excluded():
    raw = {"brands": "", "product_name": "Tea"}
    aligned = aligner.align("open_food_facts", raw)
    assert "brand" not in aligned
    assert aligned["title"] == "Tea"


def test_fingerprint_is_deterministic():
    raw = {"brandName": "X", "netContent": "100"}
    a1 = aligner.align("gs1", raw)
    a2 = aligner.align("gs1", raw)
    assert aligner.fingerprint(a1) == aligner.fingerprint(a2)


def test_coverage():
    aligned = {"brand": "TestBrand", "net_content": "500ml"}
    cov = aligner.coverage(aligned, ["brand", "net_content", "ingredients"])
    assert cov["brand"] is True
    assert cov["net_content"] is True
    assert cov["ingredients"] is False
