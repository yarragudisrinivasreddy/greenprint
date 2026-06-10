"""Insight models — how GreenPrint turns raw emissions into action."""
from dataclasses import dataclass, asdict


@dataclass
class ReductionAction:
    """A quantified behaviour change, ranked by carbon saved."""

    action: str
    category: str
    weekly_saving_kg: float
    annual_saving_kg: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FootprintSummary:
    """Aggregate view of a session's footprint used by the insight layer."""

    total_kg_co2e: float
    record_count: int
    category_totals: dict

    def to_dict(self) -> dict:
        return asdict(self)
