"""Health reporting model for the /health readiness contract."""
from dataclasses import dataclass


@dataclass
class ServiceHealth:
    """Health state of one backing service."""

    name: str
    healthy: bool
    detail: str = "ok"

    def to_dict(self) -> dict:
        return {"healthy": self.healthy, "detail": self.detail}
