from catalog_agent.merge.conflict import ConflictResolver

resolver = ConflictResolver()


def test_merchant_wins_always():
    val, reason = resolver.resolve("price", 9.99, 5.00)
    assert val == 9.99
    assert reason == "merchant_wins"


def test_merchant_wins_even_if_null():
    val, reason = resolver.resolve("inventory", None, 100)
    assert val is None
    assert reason == "merchant_wins"


def test_external_wins_for_net_content():
    val, reason = resolver.resolve("net_content", None, "500ml")
    assert val == "500ml"
    assert reason == "external_wins"


def test_external_wins_overrides_merchant():
    val, reason = resolver.resolve("ingredients", "old", "water, sugar")
    assert val == "water, sugar"
    assert reason == "external_wins"


def test_external_empty_falls_back_to_merchant():
    val, reason = resolver.resolve("net_content", "300ml", None)
    assert val == "300ml"
    assert reason == "external_empty_fallback_merchant"


def test_gap_fill_when_merchant_null():
    val, reason = resolver.resolve("description", None, "Great product")
    assert val == "Great product"
    assert reason == "gap_fill"


def test_gap_fill_skips_when_merchant_has_value():
    val, reason = resolver.resolve("brand", "MyBrand", "OtherBrand")
    assert val == "MyBrand"
    assert reason == "merchant_has_value"


def test_nutrition_wildcard_policy():
    val, reason = resolver.resolve("nutrition.energy_kcal", None, 45)
    assert val == 45
    assert reason == "external_wins"


def test_merge_produces_conflict_log():
    baseline = {"brand": "OldBrand", "price": 9.99, "net_content": None}
    external = {"brand": "NewBrand", "price": 5.00, "net_content": "500ml"}
    merged, log = resolver.merge(baseline, external)
    assert merged["price"] == 9.99          # merchant wins
    assert merged["net_content"] == "500ml" # external wins (was null)
    assert merged["brand"] == "OldBrand"    # gap_fill: merchant has value
    assert len(log) == 3


def test_unmapped_keys_skipped_in_merge():
    baseline = {}
    external = {"_unmapped": {"foo": "bar"}, "brand": "X"}
    merged, log = resolver.merge(baseline, external)
    assert "_unmapped" not in merged
    assert merged["brand"] == "X"
