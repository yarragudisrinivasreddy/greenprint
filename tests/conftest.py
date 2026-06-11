"""Shared fixtures for the GreenPrint test suite.

Google-backed services are replaced with deterministic fakes injected
through the app factory's `services` parameter — tests run offline, fast
and credential-free while exercising the real routes, registry, insight
composer and cache.
"""
from __future__ import annotations

from typing import Any

import pytest

from app import ServiceContainer, create_app
from app.services.emission_registry import EmissionFactorRegistry
from app.services.insight_cache import InsightCache
from app.services.insight_composer import InsightComposer
from app.models.activity import ActivityItem


class FakeInterpreter:
    """Deterministic stand-in for ActivityInterpreter."""

    def __init__(self) -> None:
        self.healthy = True

    def interpret_activity(self, text: str) -> list[ActivityItem]:
        return [ActivityItem(factor_key="transport.car_petrol_km", quantity=10.0, note="fake", confidence=0.9)]

    def is_healthy(self) -> bool:
        return self.healthy


class FakeNarrator:
    """Deterministic stand-in for NarrativeComposer."""

    def __init__(self) -> None:
        self.healthy = True

    def draft_eco_tip(self, estimates: list[Any], total_kg: float) -> str:
        return "Swap one car trip for the metro this week."

    def draft_simulation_narrative(self, scenario: str, saving_kg: float) -> str:
        return f"Saving {saving_kg} kgCO2e weekly is a great start."

    def is_healthy(self) -> bool:
        return self.healthy


class FakeGateway:
    """Deterministic stand-in for VertexGateway."""

    def __init__(self) -> None:
        self.healthy = True

    def get_model(self) -> Any:
        return self

    def generate_content(self, prompt: str) -> Any:
        class FakeResponse:
            def __init__(self, text: str):
                self.text = text
        return FakeResponse("Fake Gemini response")

    def is_healthy(self) -> bool:
        return self.healthy


class FakeLedger:
    """In-memory ledger mirroring FootprintLedger's contract."""

    def __init__(self) -> None:
        self.records: dict[str, list[dict[str, Any]]] = {}
        self.healthy = True

    def append(self, record: Any) -> None:
        self.records.setdefault(record.session_id, []).append(record.to_dict())

    def list_for_session(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        return list(reversed(self.records.get(session_id, [])))[:limit]

    def append_record(self, record: Any) -> None:
        self.append(record)

    def session_history(self, session_id: str) -> list[dict[str, Any]]:
        return self.list_for_session(session_id, 10)

    def is_healthy(self) -> bool:
        return self.healthy


class FakeTranslator:
    """Marks translated strings so tests can assert full-response coverage."""

    def __init__(self) -> None:
        self.healthy = True

    def translate_response(self, payload: dict[str, Any], target_language: str) -> dict[str, Any]:
        if (target_language or "en") == "en":
            return payload
        return self._mark(payload)

    def _mark(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return f"[hi]{obj}"
        if isinstance(obj, dict):
            from app.constants import NON_TRANSLATABLE_KEYS
            return {
                key: (value if key in NON_TRANSLATABLE_KEYS else self._mark(value))
                for key, value in obj.items()
            }
        if isinstance(obj, list):
            return [self._mark(item) for item in obj]
        return obj

    def is_healthy(self) -> bool:
        return self.healthy


class FakeVault:
    def __init__(self) -> None:
        self.archived: list[tuple[str, dict[str, Any]]] = []

    def archive_summary(self, session_id: str, summary: dict[str, Any]) -> bool:
        self.archived.append((session_id, summary))
        return True

    def is_healthy(self) -> bool:
        return True


class FakeSecrets:
    def get_secret(self, name: str, default: str = "") -> str:
        return default

    def is_healthy(self) -> bool:
        return True


class FakeSentiment:
    def gauge_motivation(self, text: str) -> dict[str, Any]:
        return {"score": 0.0, "tone": "neutral"}

    def is_healthy(self) -> bool:
        return True


@pytest.fixture()
def services() -> ServiceContainer:
    gateway = FakeGateway()
    return ServiceContainer(
        registry=EmissionFactorRegistry(),
        interpreter=FakeInterpreter(),
        composer=InsightComposer(),
        narrator=FakeNarrator(),
        ledger=FakeLedger(),
        translator=FakeTranslator(),
        vault=FakeVault(),
        secrets=FakeSecrets(),
        sentiment=FakeSentiment(),
        cache=InsightCache(ttl_seconds=300, max_entries=16),
        gateway=gateway,
    )


@pytest.fixture()
def app(services: ServiceContainer) -> Any:
    flask_app = create_app(services=services)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app: Any) -> Any:
    return app.test_client()
