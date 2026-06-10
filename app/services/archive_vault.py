"""ArchiveVault — Cloud Storage archival of daily footprint summaries.

Archival serves two product purposes: a durable export trail users can
request, and a decoupled corpus for future aggregate insights without
re-reading the operational Firestore collection.
"""
import json

from google.cloud import storage

from app.logging_config import get_logger

logger = get_logger(__name__)


class ArchiveVault:
    """JSON archival of tracking summaries to Cloud Storage."""

    def __init__(self, config):
        self._config = config
        self._client = None

    @property
    def client(self) -> storage.Client:
        """Lazy Cloud Storage client — created once per process."""
        if self._client is None:
            self._client = storage.Client(project=self._config.project_id)
        return self._client

    def archive_summary(self, session_id: str, summary: dict) -> bool:
        """Best-effort archive; archival must never fail a user request."""
        try:
            bucket = self.client.bucket(self._config.storage_bucket)
            blob_name = f"summaries/{session_id}/{summary.get('recorded_at', 'latest')}.json"
            bucket.blob(blob_name).upload_from_string(
                json.dumps(summary, ensure_ascii=False), content_type="application/json"
            )
            return True
        except Exception as exc:
            logger.warning("Archive skipped: %s", exc)
            return False

    def is_healthy(self) -> bool:
        try:
            return self.client is not None
        except Exception:
            return False
