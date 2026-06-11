# pylint: disable=duplicate-code
"""SecretVault — Secret Manager access for runtime configuration.

Secrets (API keys, tuning parameters) are resolved at runtime from
Secret Manager rather than baked into the image or committed to the
repository — the .env.template documents names only, never values.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import google.api_core.exceptions
import google.auth
import google.auth.exceptions
from google.cloud import secretmanager

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


class SecretVault:
    """Thin, cached reader over Secret Manager."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: secretmanager.SecretManagerServiceClient | None = None
        self._cache: dict[str, str] = {}

    @property
    def client(self) -> secretmanager.SecretManagerServiceClient:
        """Lazy Secret Manager client — created once per process."""
        if self._client is None:
            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def get_secret(self, name: str, default: str = "") -> str:
        """Read a secret's latest version; cached for the process lifetime."""
        if name in self._cache:
            return self._cache[name]
        try:
            project = self._config.project_id
            if project == "greenprint-local":
                try:
                    _, resolved_project = google.auth.default()
                    if resolved_project:
                        project = resolved_project
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
            resource = f"projects/{project}/secrets/{name}/versions/latest"
            response = self.client.access_secret_version(request={"name": resource})
            value = response.payload.data.decode("utf-8")
        except UPSTREAM_FAILURES as exc:
            logger.warning("Secret %s unavailable, using default: %s", name, exc)
            value = default
        self._cache[name] = value
        return value

    def is_healthy(self) -> bool:
        """Check connection health."""
        try:
            return self.client is not None
        except Exception:  # pylint: disable=broad-exception-caught
            # Resilience boundary: health probe must never crash the service.
            return False
