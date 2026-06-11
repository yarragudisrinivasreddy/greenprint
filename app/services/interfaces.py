# pylint: disable=too-few-public-methods
"""Service Protocols — the contracts GreenPrint's layers agree on.

Routes and the insight layer depend on these Protocols, not concrete
classes, which keeps every Google-backed service mockable in tests and
swappable in deployment.
"""
from __future__ import annotations

from typing import Protocol, Any

from app.models.activity import ActivityItem, EmissionEstimate, ActivityRecord


class ActivityInterpreter(Protocol):
    """Anything that can turn free text into ActivityItems."""

    def interpret_activity(self, text: str) -> list[ActivityItem]:
        """Interpret free text into ActivityItems."""


class EmissionEstimator(Protocol):
    """Anything that can deterministically cost ActivityItems."""

    def estimate_batch(
        self, items: list[ActivityItem]
    ) -> tuple[list[EmissionEstimate], float]:
        """Cost a batch of items; returns (estimates, total_kg_co2e)."""


class HistoryLedger(Protocol):
    """Anything that persists and recalls a session's footprint history."""

    def append_record(self, record: ActivityRecord) -> None:
        """Persist one tracking event to the ledger."""

    def session_history(self, session_id: str) -> list[dict[str, Any]]:
        """Most recent records for a session, newest first."""


class FullResponseTranslator(Protocol):
    """Anything that translates an entire structured response."""

    def translate_response(self, payload: dict[str, Any], target_language: str) -> dict[str, Any]:
        """Translate a full structured response."""
