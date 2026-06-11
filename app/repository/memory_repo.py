"""InMemoryLedger — fast, bounded in-memory implementation of LedgerRepository.

Why: Serves as a first-class repository for credential-free testing, local development
runs, and as the automatic memory fallback when Google Cloud Firestore is offline.
Includes memory-bounding policies to prevent unbounded memory growth in long-running processes.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.models.activity import ActivityRecord
from app.repository.base import LedgerRepository


class InMemoryLedger(LedgerRepository):
    """In-memory bounding database repository for activity records."""

    def __init__(self, history_window: int = 50, max_sessions: int = 256) -> None:
        self._history_window = history_window
        self._max_sessions = max_sessions
        self._storage: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()

    @property
    def records(self) -> dict[str, list[dict[str, Any]]]:
        """Backwards compatibility alias for test assertions."""
        return self._storage

    def append(self, record: ActivityRecord) -> None:
        """Add a record, capping per-session history and evicting oldest sessions."""
        session_id = record.session_id
        if session_id in self._storage:
            self._storage.move_to_end(session_id)
        else:
            self._storage[session_id] = []

        history = self._storage[session_id]
        history.append(record.to_dict())

        # Cap records per session
        if len(history) > self._history_window:
            history.pop(0)

        # Evict oldest sessions beyond limit
        while len(self._storage) > self._max_sessions:
            self._storage.popitem(last=False)

    def list_for_session(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        """List records for a session, returning newest first."""
        if session_id not in self._storage:
            return []
        self._storage.move_to_end(session_id)
        records = self._storage[session_id]
        # Return reversed (newest first) capped at limit
        return list(reversed(records))[:limit]

    def is_healthy(self) -> bool:
        """In-memory storage is local and always healthy."""
        return True
