"""Domain exception hierarchy and its HTTP mapping."""
from __future__ import annotations

from typing import Any

import pytest

from app.exceptions import (
    EstimationError,
    GreenPrintError,
    LedgerError,
    TranslationError,
    ValidationError,
)


class TestHierarchy:
    @pytest.mark.parametrize(
        "exc_class", [ValidationError, EstimationError, TranslationError, LedgerError]
    )
    def test_all_domain_errors_extend_base(self, exc_class: Any) -> None:
        assert issubclass(exc_class, GreenPrintError)

    def test_validation_error_maps_to_400(self) -> None:
        assert ValidationError("bad").status_code == 400

    def test_validation_error_exposes_its_message(self) -> None:
        assert ValidationError("Provide text").public_message == "Provide text"

    def test_upstream_errors_map_to_502(self) -> None:
        assert EstimationError().status_code == 502
        assert TranslationError().status_code == 502
        assert LedgerError().status_code == 502

    def test_base_error_has_safe_public_message(self) -> None:
        # Internal detail never leaks through the public message default.
        assert "internal" in GreenPrintError().public_message.lower()


class TestErrorContract:
    def test_domain_error_returns_stable_json(self, client: Any) -> None:
        response = client.post("/api/track", json={})
        body = response.get_json()
        assert response.status_code == 400
        assert set(body) == {"status", "message"}

    def test_payload_too_large_413(self, client: Any) -> None:
        oversized = {"text": "x" * (11 * 1024)}
        response = client.post("/api/track", json=oversized)
        assert response.status_code == 413
        assert response.get_json()["status"] == "error"
