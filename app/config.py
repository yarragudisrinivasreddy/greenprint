"""Immutable runtime configuration for GreenPrint.

Configuration is frozen at startup so no request handler can mutate
global state — a deliberate guard for multi-worker Cloud Run deployments.
"""
import os
import google.auth
from dataclasses import dataclass, field


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


def load_config() -> Config:
    """Build the immutable configuration snapshot for this process."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        try:
            _, project_id = google.auth.default()
        except Exception:
            pass
    if not project_id:
        project_id = "greenprint-local"

    bucket = os.environ.get("GREENPRINT_BUCKET")
    if not bucket:
        if project_id == "greenprint-local":
            bucket = "greenprint-archive"
        else:
            bucket = f"greenprint-archive-{project_id}"

    return Config(project_id=project_id, storage_bucket=bucket)
