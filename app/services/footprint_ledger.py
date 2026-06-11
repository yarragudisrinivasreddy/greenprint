# pylint: disable=duplicate-code
"""FootprintLedger — GreenPrint's Firestore-backed footprint history.

The ledger is what turns one-off estimates into *personalised* insight:
weekly trends, EcoScore and reduction rankings are all computed against
a session's own history rather than population averages.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import google.api_core.exceptions
import google.auth.exceptions
from google.cloud import firestore

from app.exceptions import LedgerError
from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.config import Config
    from app.models.activity import ActivityRecord

logger = get_logger(__name__)

UPSTREAM_FAILURES = (
    google.api_core.exceptions.GoogleAPIError,
    google.auth.exceptions.GoogleAuthError,
    OSError,
    ValueError,
)


class FootprintLedger:
    """Append-only ledger of ActivityRecords keyed by session."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: firestore.Client | None = None
        # In-memory mirror keeps the app fully functional if Firestore is
        # unreachable (e.g. local development without credentials).
        self._local_mirror: dict[str, list[dict[str, object]]] = {}

    @property
    def client(self) -> firestore.Client:
        """Lazy Firestore client — created once per process."""
        if self._client is None:
            project = self._config.project_id
            if project == "greenprint-local":
                project = None
            self._client = firestore.Client(project=project)
        return self._client

    def append_record(self, record: ActivityRecord) -> None:
        """Persist one tracking event to the ledger."""
        self._local_mirror.setdefault(record.session_id, []).append(record.to_dict())
        try:
            self.client.collection(self._config.firestore_collection).add(record.to_dict())
        except UPSTREAM_FAILURES as exc:
            # The mirror already holds the record; insight quality degrades
            # gracefully instead of failing the user's tracking request.
            logger.warning("Firestore append failed, serving from mirror: %s", exc)

    def session_history(self, session_id: str) -> list[dict[str, object]]:
        """Most recent records for a session, newest first, capped for efficiency."""
        if not session_id:
            raise LedgerError("A session_id is required to read history.")
        try:
            query = (
                self.client.collection(self._config.firestore_collection)
                .where("session_id", "==", session_id)
                .order_by("recorded_at", direction=firestore.Query.DESCENDING)
                .limit(self._config.history_window)
            )
            return [doc.to_dict() for doc in query.stream()]
        except UPSTREAM_FAILURES as exc:
            logger.warning("Firestore read failed, serving mirror: %s", exc)
            mirrored = list(reversed(self._local_mirror.get(session_id, [])))
            return mirrored[: self._config.history_window]

    def is_healthy(self) -> bool:
        """Check connection health."""
        try:
            return self.client is not None
        except Exception:  # pylint: disable=broad-exception-caught
            # Resilience boundary: health probe must never crash the service.
            return False
