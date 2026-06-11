"""Immutable runtime configuration for GreenPrint.

Configuration is frozen at startup so no request handler can mutate
global state — a deliberate guard for multi-worker Cloud Run deployments.
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass, field

import google.auth
import google.auth.exceptions

from app.logging_config import get_logger

logger = get_logger(__name__)


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


@functools.lru_cache(maxsize=1)
def resolve_project_id() -> str:
    """Resolve the GCP project ID once per process (env first, ADC second)."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project_id:
        return project_id
    if "PYTEST_CURRENT_TEST" in os.environ:
        # Tests must never query the ADC metadata server (offline hang).
        return "greenprint-local"
    try:
        _, resolved = google.auth.default()
        if resolved:
            return resolved
    except (google.auth.exceptions.GoogleAuthError, OSError) as exc:
        logger.warning("ADC project resolution failed; using local default: %s", exc)
    return "greenprint-local"


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
