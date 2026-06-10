"""FootprintLedger — GreenPrint's Firestore-backed footprint history.

The ledger is what turns one-off estimates into *personalised* insight:
weekly trends, EcoScore and reduction rankings are all computed against
a session's own history rather than population averages.
"""
from google.cloud import firestore

from app.exceptions import LedgerError
from app.logging_config import get_logger
from app.models.activity import ActivityRecord

logger = get_logger(__name__)


class FootprintLedger:
    """Append-only ledger of ActivityRecords keyed by session."""

    def __init__(self, config):
        self._config = config
        self._client = None
        # In-memory mirror keeps the app fully functional if Firestore is
        # unreachable (e.g. local development without credentials).
        self._local_mirror = {}

    @property
    def client(self) -> firestore.Client:
        """Lazy Firestore client — created once per process."""
        if self._client is None:
            self._client = firestore.Client(project=self._config.project_id)
        return self._client

    def append_record(self, record: ActivityRecord) -> None:
        """Persist one tracking event to the ledger."""
        self._local_mirror.setdefault(record.session_id, []).append(record.to_dict())
        try:
            self.client.collection(self._config.firestore_collection).add(record.to_dict())
        except Exception as exc:
            # The mirror already holds the record; insight quality degrades
            # gracefully instead of failing the user's tracking request.
            logger.warning("Firestore append failed, serving from mirror: %s", exc)

    def session_history(self, session_id: str) -> list:
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
        except Exception as exc:
            logger.warning("Firestore read failed, serving mirror: %s", exc)
            mirrored = list(reversed(self._local_mirror.get(session_id, [])))
            return mirrored[: self._config.history_window]

    def is_healthy(self) -> bool:
        try:
            return self.client is not None
        except Exception:
            return False
