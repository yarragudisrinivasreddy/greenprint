"""Shared fixtures for the GreenPrint test suite.

Google-backed services are replaced with deterministic fakes injected
through the app factory's `services` parameter — tests run offline, fast
and credential-free while exercising the real routes, registry, insight
composer and cache.
"""
import pytest

from app import ServiceContainer, create_app
from app.services.emission_registry import EmissionFactorRegistry
from app.services.insight_cache import InsightCache
from app.services.insight_composer import InsightComposer
from app.models.activity import ActivityItem


class FakeEngine:
    """Deterministic stand-in for CarbonIntelligenceEngine."""

    def __init__(self):
        self.healthy = True

    def interpret_activity(self, text):
        return [ActivityItem(factor_key="transport.car_petrol_km", quantity=10.0, note="fake", confidence=0.9)]

    def draft_eco_tip(self, estimates, total_kg):
        return "Swap one car trip for the metro this week."

    def draft_simulation_narrative(self, scenario, saving_kg):
        return f"Saving {saving_kg} kgCO2e weekly is a great start."

    def is_healthy(self):
        return self.healthy


class FakeLedger:
    """In-memory ledger mirroring FootprintLedger's contract."""

    def __init__(self):
        self.records = {}
        self.healthy = True

    def append_record(self, record):
        self.records.setdefault(record.session_id, []).append(record.to_dict())

    def session_history(self, session_id):
        return list(reversed(self.records.get(session_id, [])))

    def is_healthy(self):
        return self.healthy


class FakeTranslator:
    """Marks translated strings so tests can assert full-response coverage."""

    def __init__(self):
        self.healthy = True

    def translate_response(self, payload, target_language):
        if (target_language or "en") == "en":
            return payload
        return self._mark(payload)

    def _mark(self, obj):
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

    def is_healthy(self):
        return self.healthy


class FakeVault:
    def __init__(self):
        self.archived = []

    def archive_summary(self, session_id, summary):
        self.archived.append((session_id, summary))
        return True

    def is_healthy(self):
        return True


class FakeSecrets:
    def get_secret(self, name, default=""):
        return default

    def is_healthy(self):
        return True


class FakeSentiment:
    def gauge_motivation(self, text):
        return {"score": 0.0, "tone": "neutral"}

    def is_healthy(self):
        return True


@pytest.fixture()
def services():
    return ServiceContainer(
        registry=EmissionFactorRegistry(),
        engine=FakeEngine(),
        composer=InsightComposer(),
        ledger=FakeLedger(),
        translator=FakeTranslator(),
        vault=FakeVault(),
        secrets=FakeSecrets(),
        sentiment=FakeSentiment(),
        cache=InsightCache(ttl_seconds=300, max_entries=16),
    )


@pytest.fixture()
def app(services):
    flask_app = create_app(services=services)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
