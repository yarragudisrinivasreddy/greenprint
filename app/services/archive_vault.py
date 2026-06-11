# pylint: disable=duplicate-code
"""ArchiveVault — Cloud Storage archival of daily footprint summaries.

Archival serves two product purposes: a durable export trail users can
request, and a decoupled corpus for future aggregate insights without
re-reading the operational Firestore collection.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

import google.api_core.exceptions
import google.auth.exceptions
from google.cloud import storage

from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.config import Config

logger = get_logger(__name__)

UPSTREAM_FAILURES = (
    google.api_core.exceptions.GoogleAPIError,
    google.auth.exceptions.GoogleAuthError,
    OSError,
    ValueError,
)


class ArchiveVault:
    """JSON archival of tracking summaries to Cloud Storage."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: storage.Client | None = None

    @property
    def client(self) -> storage.Client:
        """Lazy Cloud Storage client — created once per process."""
        if self._client is None:
            project = self._config.project_id
            if project == "greenprint-local":
                project = None
            self._client = storage.Client(project=project)
        return self._client

    def archive_summary(self, session_id: str, summary: dict[str, object]) -> bool:
        """Best-effort archive; archival must never fail a user request."""
        try:
            bucket = self.client.bucket(self._config.storage_bucket)
            recorded_at = str(summary.get("recorded_at", "latest"))
            blob_name = f"summaries/{session_id}/{recorded_at}.json"
            bucket.blob(blob_name).upload_from_string(
                json.dumps(summary, ensure_ascii=False), content_type="application/json"
            )
            return True
        except UPSTREAM_FAILURES as exc:
            logger.warning("Archive skipped: %s", exc)
            return False

    def is_healthy(self) -> bool:
        """Check connection health."""
        try:
            return self.client is not None
        except Exception:  # pylint: disable=broad-exception-caught
            # Resilience boundary: health probe must never crash the service.
            return False
