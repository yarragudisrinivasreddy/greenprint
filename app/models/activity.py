"""Activity and emission models — the core ledger records of GreenPrint.

An `ActivityItem` is what the intelligence engine extracts from user
input; an `EmissionEstimate` is the registry's deterministic costing of
that item; an `ActivityRecord` is the persisted ledger entry.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ActivityItem:
    """A single interpreted activity, normalised to a registry factor."""

    factor_key: str
    quantity: float
    note: str = ""
    confidence: float = 1.0  # 1.0 = exact factor match, lower = nearest-factor guess.

    def to_dict(self) -> dict[str, Any]:
        """Convert the ActivityItem model to a serialized dictionary."""
        return asdict(self)


@dataclass
class EmissionEstimate:
    """Deterministic emission costing for one activity item."""

    factor_key: str
    label: str
    category: str
    quantity: float
    unit: str
    emission_kg_co2e: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        """Convert the EmissionEstimate model to a serialized dictionary."""
        return asdict(self)


@dataclass
class ActivityRecord:
    """A persisted footprint ledger entry for one tracking request."""

    session_id: str
    estimates: list[EmissionEstimate] = field(default_factory=list)
    total_kg_co2e: float = 0.0
    source_text: str = ""
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert the ActivityRecord model to a serialized dictionary."""
        return {
            "session_id": self.session_id,
            "estimates": [e.to_dict() if hasattr(e, "to_dict") else e for e in self.estimates],
            "total_kg_co2e": self.total_kg_co2e,
            "source_text": self.source_text,
            "recorded_at": self.recorded_at,
        }
