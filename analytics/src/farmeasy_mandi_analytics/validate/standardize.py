"""Traceable text standardization for market, commodity, and location names."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_WHITESPACE = re.compile(r"\s+")
_WORD_BOUNDARIES = re.compile(r"([-/'&])")
_KNOWN_ACRONYMS = frozenset({"APMC", "FPO", "ICAR", "NABARD", "NCDC", "NAFED"})


def is_missing_text(value: Any) -> bool:
    """Return whether a raw source value is absent without converting it to text."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def collapse_whitespace(value: Any) -> str | None:
    """Normalize Unicode and internal whitespace while preserving source words."""
    if is_missing_text(value):
        return None
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", str(value)).strip())


def normalize_name_key(value: Any) -> str | None:
    """Produce a case-insensitive, whitespace-stable key for matching dimensions."""
    cleaned = collapse_whitespace(value)
    return cleaned.casefold() if cleaned else None


def _display_case(value: str) -> str:
    """Make ordinary casing consistent while retaining known market acronyms."""

    def render_part(part: str) -> str:
        if _WORD_BOUNDARIES.fullmatch(part):
            return part
        upper_part = part.upper()
        if upper_part in _KNOWN_ACRONYMS:
            return upper_part
        return part.lower().capitalize()

    rendered_tokens: list[str] = []
    for token in value.split(" "):
        parts = _WORD_BOUNDARIES.split(token)
        rendered_parts = [render_part(part) for part in parts]
        rendered_tokens.append("".join(rendered_parts))
    return " ".join(rendered_tokens)


@dataclass(slots=True)
class NameStandardizer:
    """Apply optional, source-verified aliases after safe baseline cleanup.

    The original values remain in the transformed dataframe. This object only
    determines the canonical display text and matching key used by dimensions.
    """

    aliases: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: Path | str) -> NameStandardizer:
        config_path = Path(path)
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read name alias configuration {config_path}.") from error
        if not isinstance(payload, Mapping):
            raise ValueError("Name alias configuration must contain a JSON object.")

        aliases: dict[str, dict[str, str]] = {}
        for field_name, mapping in payload.items():
            if field_name in {"config_version", "usage"}:
                continue
            if not isinstance(mapping, Mapping):
                raise ValueError(f"Aliases for {field_name!r} must be an object.")
            aliases[str(field_name)] = {
                key: value
                for raw_key, raw_value in mapping.items()
                if (key := normalize_name_key(raw_key)) is not None
                and isinstance(raw_value, str)
                and normalize_name_key(raw_value) is not None
                for value in [collapse_whitespace(raw_value)]
                if value is not None
            }
        return cls(aliases=aliases)

    def standardize(self, field_name: str, value: Any) -> tuple[str | None, str | None]:
        """Return `(canonical_display, normalized_key)` for one source value."""
        cleaned = collapse_whitespace(value)
        if cleaned is None:
            return None, None

        normalized = normalize_name_key(cleaned)
        assert normalized is not None
        alias = self.aliases.get(field_name, {}).get(normalized)
        canonical = alias if alias is not None else _display_case(cleaned)
        return canonical, normalize_name_key(canonical)
