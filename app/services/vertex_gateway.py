"""VertexGateway — owns Vertex AI initialization and generative model access.

Why: Concentrates Vertex AI client creation and environment setup in a single,
shared class to avoid redundant initialization and simplify mock test setups.
"""
# pylint: disable=duplicate-code
from __future__ import annotations

from typing import TYPE_CHECKING

import vertexai
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel

from app.config import resolve_project_id

if TYPE_CHECKING:
    from app.config import Config


class VertexGateway:
    """Gateway managing Vertex AI and GenerativeModel initialization."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._model: GenerativeModel | None = None
        self._initialized = False

    def get_model(self) -> GenerativeModel:
        """Initialise Vertex AI lazily — once per process, never per request."""
        if not self._initialized:
            project = resolve_project_id()
            proj_arg = None if project == "greenprint-local" else project
            vertexai.init(project=proj_arg, location=self._config.location)
            aiplatform.init(project=proj_arg, location=self._config.location)
            self._model = GenerativeModel(self._config.gemini_model_name)
            self._initialized = True
        assert self._model is not None
        return self._model

    def is_healthy(self) -> bool:
        """Verify the gateway is ready to initialize the model."""
        try:
            self.get_model()
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            # Resilience boundary: health probe must never crash the service.
            return False
