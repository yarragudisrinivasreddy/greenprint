"""Typed constants for the GreenPrint carbon domain.

Centralising category names, language codes and unit symbols removes
magic strings from services and keeps the translation exclusion set in
one auditable place.
"""
from __future__ import annotations

from enum import Enum


class ActivityCategory(str, Enum):
    """Top-level lifestyle categories an individual's footprint splits into."""

    TRANSPORT = "transport"
    FOOD = "food"
    ENERGY = "energy"
    SHOPPING = "shopping"


SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "hi", "te", "ta", "kn", "bn", "mr")
DEFAULT_LANGUAGE: str = "en"

# Strings that must never be translated: unit symbols lose scientific
# meaning and hashtags lose platform function in non-Latin scripts.
UNIT_SYMBOLS: tuple[str, ...] = ("kgCO2e", "kgCO₂e", "kWh", "km", "kg")
PROTECTED_PREFIXES: tuple[str, ...] = ("#",)

# JSON keys whose values are machine-readable identifiers, never prose.
NON_TRANSLATABLE_KEYS: frozenset[str] = frozenset(
    {
        "factor_key",
        "category",
        "session_id",
        "language",
        "status",
        "unit",
        "weekly_trend_svg",
    }
)

ECO_SCORE_MAX: int = 100
