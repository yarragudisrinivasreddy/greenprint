"""FootprintLedger — coordinating selector repository.

Why: Coordinates the database (Firestore) ledger repository and the in-memory fallback
repository. If Firestore is offline or fails authentication, it delegates to InMemoryLedger
to keep the application fully functional (graceful degradation).
"""
# pylint: disable=duplicate-code
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.exceptions import LedgerError
from app.logging_config import get_logger
from app.models.activity import ActivityRecord
from app.repository.base import LedgerRepository
from app.repository.firestore_repo import UPSTREAM_FAILURES, FirestoreLedger
from app.repository.memory_repo import InMemoryLedger

if TYPE_CHECKING:
    from app.config import Config

logger = get_logger(__name__)


class FootprintLedger(LedgerRepository):
    """Repository coordinator with Firestore priority and In-Memory fallback."""

    def __init__(
        self, firestore_repo: FirestoreLedger, memory_repo: InMemoryLedger, config: Config
    ) -> None:
        self._firestore = firestore_repo
        self._memory = memory_repo
        self._config = config

    def append(self, record: ActivityRecord) -> None:
        """Persist a tracking event. Always writes to memory for mirror backup."""
        self._memory.append(record)
        try:
            self._firestore.append(record)
        except UPSTREAM_FAILURES as exc:
            logger.warning("Firestore append failed, serving from mirror: %s", exc)

    def list_for_session(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        """Retrieve most recent records for a session, falling back to memory if Firestore fails."""
        if not session_id:
            raise LedgerError("A session_id is required to read history.")
        try:
            return self._firestore.list_for_session(session_id, limit)
        except UPSTREAM_FAILURES as exc:
            logger.warning("Firestore read failed, serving from mirror: %s", exc)
            return self._memory.list_for_session(session_id, limit)

    def append_record(self, record: ActivityRecord) -> None:
        """Compatibility wrapper delegating to append."""
        self.append(record)

    def session_history(self, session_id: str) -> list[dict[str, Any]]:
        """Compatibility wrapper delegating to list_for_session."""
        return self.list_for_session(session_id, self._config.history_window)

    def is_healthy(self) -> bool:
        """Check connection health of the firestore repository."""
        return self._firestore.is_healthy()
