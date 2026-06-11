"""Insight models — how GreenPrint turns raw emissions into action."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ReductionAction:
    """A quantified behaviour change, ranked by carbon saved."""

    action: str
    category: str
    weekly_saving_kg: float
    annual_saving_kg: float

    def to_dict(self) -> dict[str, Any]:
        """Convert the ReductionAction model to a serialized dictionary."""
        return asdict(self)


@dataclass
class FootprintSummary:
    """Aggregate view of a session's footprint used by the insight layer."""

    total_kg_co2e: float
    record_count: int
    category_totals: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        """Convert the FootprintSummary model to a serialized dictionary."""
        return asdict(self)
