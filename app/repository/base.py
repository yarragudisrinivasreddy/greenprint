"""LedgerRepository — abstract interface protocol for database operations.

Why: Decouples the application code and routes from direct Firestore client dependency,
permitting in-memory testing and swappable storage backends.
"""
# pylint: disable=too-few-public-methods
from __future__ import annotations

from typing import Any, Protocol

from app.models.activity import ActivityRecord


class LedgerRepository(Protocol):
    """Protocol defining persistence and retrieval operations for activity records."""

    def append(self, record: ActivityRecord) -> None:
        """Persist one tracking event to the ledger."""

    def list_for_session(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        """Retrieve the most recent records for a session, newest first."""
