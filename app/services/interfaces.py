"""Service Protocols — the contracts GreenPrint's layers agree on.

Routes and the insight layer depend on these Protocols, not concrete
classes, which keeps every Google-backed service mockable in tests and
swappable in deployment.
"""
from typing import Protocol

from app.models.activity import ActivityItem, EmissionEstimate


class ActivityInterpreter(Protocol):
    """Anything that can turn free text into ActivityItems."""

    def interpret_activity(self, text: str) -> list[ActivityItem]:
        ...


class EmissionEstimator(Protocol):
    """Anything that can deterministically cost ActivityItems."""

    def estimate_batch(self, items: list[ActivityItem]) -> tuple[list[EmissionEstimate], float]:
        ...


class HistoryLedger(Protocol):
    """Anything that persists and recalls a session's footprint history."""

    def append_record(self, record) -> None:
        ...

    def session_history(self, session_id: str) -> list:
        ...


class FullResponseTranslator(Protocol):
    """Anything that translates an entire structured response."""

    def translate_response(self, payload: dict, target_language: str) -> dict:
        ...
