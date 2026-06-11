"""FirestoreLedger — Firestore-backed implementation of the ledger repository.

Why: Provides robust persistence to Google Cloud Firestore in production environments
while keeping database logic isolated from routing.
"""
# pylint: disable=duplicate-code
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import google.api_core.exceptions
import google.auth.exceptions
from google.cloud import firestore

from app.models.activity import ActivityRecord
from app.repository.base import LedgerRepository

if TYPE_CHECKING:
    from app.config import Config

UPSTREAM_FAILURES = (
    google.api_core.exceptions.GoogleAPIError,
    google.auth.exceptions.GoogleAuthError,
    OSError,
    ValueError,
)


class FirestoreLedger(LedgerRepository):
    """Firestore-backed repository storing activity logs."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: firestore.Client | None = None

    @property
    def client(self) -> firestore.Client:
        """Lazy Firestore client — created once per process."""
        if self._client is None:
            project = self._config.project_id
            if project == "greenprint-local":
                project = None
            self._client = firestore.Client(project=project)
        return self._client

    def append(self, record: ActivityRecord) -> None:
        """Add a record to the Firestore collection."""
        self.client.collection(self._config.firestore_collection).add(record.to_dict())

    def list_for_session(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        """Query Firestore for a session's history up to a limit."""
        query = (
            self.client.collection(self._config.firestore_collection)
            .where("session_id", "==", session_id)
            .order_by("recorded_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [doc.to_dict() for doc in query.stream()]

    def is_healthy(self) -> bool:
        """Check connection health."""
        try:
            return self.client is not None
        except Exception:  # pylint: disable=broad-exception-caught
            # Resilience boundary: health probe must never crash the service.
            return False
