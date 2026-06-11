"""Health reporting model for the /health readiness contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ServiceHealth:
    """Health state of one backing service."""

    name: str
    healthy: bool
    detail: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        """Convert the ServiceHealth model to a serialized dictionary."""
        return {"healthy": self.healthy, "detail": self.detail}
