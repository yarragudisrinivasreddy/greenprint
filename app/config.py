"""Immutable runtime configuration for GreenPrint.

Configuration is frozen at startup so no request handler can mutate
global state — a deliberate guard for multi-worker Cloud Run deployments.
"""
import os
from dataclasses import dataclass, field
from unittest.mock import Mock

import google.auth
import google.auth.exceptions


@dataclass(frozen=True)
class Config:
    """Frozen application configuration resolved from the environment."""

    project_id: str
    storage_bucket: str
    location: str = field(
        default_factory=lambda: os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-south1")
    )
    gemini_model_name: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    )
    firestore_collection: str = "footprint_ledger"
    insight_cache_ttl_seconds: int = 300
    insight_cache_max_entries: int = 256
    max_request_bytes: int = 10 * 1024  # Oversized payloads are rejected with 413.
    history_window: int = 50  # Cap Firestore reads — efficiency over completeness.


_RESOLVED_PROJECT_ID: str | None = None


def resolve_project_id() -> str:
    """Resolve and cache the project ID from environment or ADC.

    Why: Centralizes credentials resolution to prevent hanging pytest runs
    and logs authentication errors securely.
    """
    global _RESOLVED_PROJECT_ID

    is_mocked = isinstance(google.auth.default, Mock)

    if _RESOLVED_PROJECT_ID is not None and not is_mocked:
        return _RESOLVED_PROJECT_ID

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")

    # Avoid querying metadata server/ADC during pytest runs to prevent offline hangs.
    is_testing = "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("FLASK_ENV") == "testing"

    if not project_id and (not is_testing or is_mocked):
        try:
            _, resolved = google.auth.default()
            if resolved:
                project_id = resolved
        except (google.auth.exceptions.GoogleAuthError, OSError) as exc:
            from app.logging_config import get_logger
            get_logger(__name__).warning(
                "Google credentials resolution failed (falling back to local): %s", exc
            )

    if not project_id:
        project_id = "greenprint-local"

    if not is_mocked:
        _RESOLVED_PROJECT_ID = project_id
    return project_id


def load_config() -> Config:
    """Build the immutable configuration snapshot for this process."""
    project_id = resolve_project_id()

    bucket = os.environ.get("GREENPRINT_BUCKET")
    if not bucket:
        if project_id == "greenprint-local":
            bucket = "greenprint-archive"
        else:
            bucket = f"greenprint-archive-{project_id}"

    return Config(project_id=project_id, storage_bucket=bucket)
