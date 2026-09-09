from farmeasy_mandi_analytics.contracts import CANONICAL_PRICE_FIELDS, REQUIRED_PRICE_FIELDS


def test_required_fields_are_a_subset_of_the_canonical_contract() -> None:
    assert set(REQUIRED_PRICE_FIELDS).issubset(CANONICAL_PRICE_FIELDS)


def test_arrival_fields_are_optional_to_keep_price_analytics_operational() -> None:
    assert "arrival_quantity" in CANONICAL_PRICE_FIELDS
    assert "arrival_quantity" not in REQUIRED_PRICE_FIELDS
