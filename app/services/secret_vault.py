"""SecretVault — Secret Manager access for runtime configuration.

Secrets (API keys, tuning parameters) are resolved at runtime from
Secret Manager rather than baked into the image or committed to the
repository — the .env.template documents names only, never values.
"""
from google.cloud import secretmanager

from app.logging_config import get_logger

logger = get_logger(__name__)


class SecretVault:
    """Thin, cached reader over Secret Manager."""

    def __init__(self, config):
        self._config = config
        self._client = None
        self._cache = {}

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
            resource = f"projects/{self._config.project_id}/secrets/{name}/versions/latest"
            value = self.client.access_secret_version(request={"name": resource}).payload.data.decode("utf-8")
        except Exception as exc:
            logger.warning("Secret %s unavailable, using default: %s", name, exc)
            value = default
        self._cache[name] = value
        return value

    def is_healthy(self) -> bool:
        try:
            return self.client is not None
        except Exception:
            return False
