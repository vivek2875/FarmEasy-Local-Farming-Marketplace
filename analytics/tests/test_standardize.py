import json

import pytest

from farmeasy_mandi_analytics.validate.standardize import (
    NameStandardizer,
    collapse_whitespace,
    normalize_name_key,
)


def test_standardizer_applies_only_documented_aliases_and_safe_casing(tmp_path) -> None:
    aliases_path = tmp_path / "aliases.json"
    aliases_path.write_text(
        json.dumps({"state": {"orissa": "Odisha"}, "market": {}}),
        encoding="utf-8",
    )

    standardizer = NameStandardizer.from_json(aliases_path)

    assert standardizer.standardize("state", "  ORISSA ") == ("Odisha", "odisha")
    assert standardizer.standardize("market", "  gorantla   apmc ") == (
        "Gorantla APMC",
        "gorantla apmc",
    )
    assert standardizer.standardize("commodity", "TOMATO") == ("Tomato", "tomato")


def test_text_normalization_preserves_missing_values_and_collapses_unicode_whitespace() -> None:
    assert collapse_whitespace(None) is None
    assert collapse_whitespace(" \u00a0  Mysuru\tAPMC  ") == "Mysuru APMC"
    assert normalize_name_key(" MYSURU  APMC ") == "mysuru apmc"


def test_invalid_alias_configuration_fails_with_a_clear_error(tmp_path) -> None:
    aliases_path = tmp_path / "aliases.json"
    aliases_path.write_text(json.dumps({"state": ["not", "a", "mapping"]}), encoding="utf-8")

    with pytest.raises(ValueError, match="Aliases"):
        NameStandardizer.from_json(aliases_path)
