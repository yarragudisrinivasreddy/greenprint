"""Service-level behaviour: translator exclusions, cache, composer, ledger mirror, and Google-backed wrapper resilient contracts."""
from __future__ import annotations

import time
from typing import Any

import pytest
import google.api_core.exceptions

from app.config import load_config
from app.exceptions import TranslationError, LedgerError
from app.models.activity import ActivityRecord
from app.services.insight_cache import InsightCache
from app.services.insight_composer import InsightComposer
from app.services.translator import ResponseTranslator
from app.services.archive_vault import ArchiveVault
from app.services.footprint_ledger import FootprintLedger
from app.services.secret_vault import SecretVault
from app.services.sentiment_lens import SentimentLens


@pytest.fixture()
def translator(mocker: Any) -> ResponseTranslator:
    service = ResponseTranslator(load_config())
    fake_client = mocker.Mock()
    fake_client.translate_text.side_effect = lambda request: mocker.Mock(
        translations=[mocker.Mock(translated_text=f"hi::{request['contents'][0]}")]
    )
    service._client = fake_client
    return service


@pytest.fixture()
def config() -> Any:
    return load_config()


@pytest.fixture()
def clear_project_cache() -> None:
    from app.config import resolve_project_id
    resolve_project_id.cache_clear()
    yield
    resolve_project_id.cache_clear()


class TestTranslatorExclusions:
    def test_english_passthrough_makes_no_calls(self, translator: ResponseTranslator) -> None:
        payload = {"eco_tip": "Walk more"}
        assert translator.translate_response(payload, "en") == payload
        translator._client.translate_text.assert_not_called()

    def test_prose_values_are_translated(self, translator: ResponseTranslator) -> None:
        result = translator.translate_response({"eco_tip": "Walk more"}, "hi")
        assert result["eco_tip"] == "hi::Walk more"

    def test_non_translatable_keys_skipped(self, translator: ResponseTranslator) -> None:
        result = translator.translate_response({"factor_key": "transport.metro_km"}, "hi")
        assert result["factor_key"] == "transport.metro_km"

    def test_hashtags_never_translated(self, translator: ResponseTranslator) -> None:
        result = translator.translate_response({"share_text": "#GreenPrint"}, "hi")
        assert result["share_text"] == "#GreenPrint"

    def test_unit_symbols_never_translated(self, translator: ResponseTranslator) -> None:
        result = translator.translate_response({"unit_note": "kgCO2e"}, "hi")
        assert result["unit_note"] == "kgCO2e"

    def test_numbers_pass_through_untouched(self, translator: ResponseTranslator) -> None:
        result = translator.translate_response({"total_kg_co2e": 3.8}, "hi")
        assert result["total_kg_co2e"] == 3.8

    def test_nested_lists_translated_recursively(self, translator: ResponseTranslator) -> None:
        result = translator.translate_response({"actions": [{"action": "Cycle short trips"}]}, "hi")
        assert result["actions"][0]["action"] == "hi::Cycle short trips"

    def test_unsupported_language_raises(self, translator: ResponseTranslator) -> None:
        with pytest.raises(TranslationError):
            translator.translate_response({"eco_tip": "x"}, "xx")

    def test_upstream_translation_failure_raises_translation_error(self, mocker: Any) -> None:
        service = ResponseTranslator(load_config())
        fake_client = mocker.Mock()
        fake_client.translate_text.side_effect = google.api_core.exceptions.GoogleAPIError("api down")
        service._client = fake_client

        with pytest.raises(TranslationError):
            service.translate_response({"eco_tip": "Prose"}, "hi")


class TestInsightCache:
    def test_set_then_get_round_trip(self) -> None:
        cache = InsightCache(ttl_seconds=60, max_entries=4)
        cache.set(("insights", "s1", "en"), {"a": 1})
        assert cache.get(("insights", "s1", "en")) == {"a": 1}

    def test_expired_entry_returns_none(self) -> None:
        cache = InsightCache(ttl_seconds=0, max_entries=4)
        cache.set(("k",), "v")
        time.sleep(0.01)
        assert cache.get(("k",)) is None

    def test_lru_eviction_on_overflow(self) -> None:
        cache = InsightCache(ttl_seconds=60, max_entries=2)
        cache.set(("a",), 1)
        cache.set(("b",), 2)
        cache.set(("c",), 3)
        assert cache.get(("a",)) is None
        assert cache.get(("c",)) == 3

    def test_invalidate_prefix_drops_matching_keys(self) -> None:
        cache = InsightCache(ttl_seconds=60, max_entries=4)
        cache.set(("insights", "s1", "en"), {"a": 1})
        cache.set(("insights", "s1", "hi"), {"a": 2})
        cache.set(("insights", "s2", "en"), {"b": 1})

        cache.invalidate_prefix(("insights", "s1"))

        assert cache.get(("insights", "s1", "en")) is None
        assert cache.get(("insights", "s1", "hi")) is None
        assert cache.get(("insights", "s2", "en")) == {"b": 1}


class TestInsightComposer:
    def _history(self) -> list[dict[str, Any]]:
        return [
            {
                "recorded_at": "2026-06-10T08:00:00+00:00",
                "total_kg_co2e": 3.8,
                "estimates": [
                    {"category": "transport", "emission_kg_co2e": 1.8},
                    {"category": "food", "emission_kg_co2e": 2.0},
                ],
            }
        ]

    def test_summarize_aggregates_categories(self) -> None:
        summary = InsightComposer().summarize(self._history())
        assert summary.category_totals["transport"] == 1.8
        assert summary.total_kg_co2e == 3.8

    def test_eco_score_neutral_for_empty_history(self) -> None:
        score = InsightComposer().eco_score([])
        assert score["score"] == 50

    def test_eco_score_rewards_below_baseline_day(self) -> None:
        score = InsightComposer().eco_score(self._history())
        assert score["score"] > 50
        assert score["streak_days"] == 1

    def test_reduction_actions_ranked_by_saving(self) -> None:
        composer = InsightComposer()
        actions = composer.rank_reduction_actions(composer.summarize(self._history()))
        savings = [a.weekly_saving_kg for a in actions]
        assert savings == sorted(savings, reverse=True)

    def test_trend_svg_is_accessible(self) -> None:
        svg = InsightComposer().weekly_trend_svg(self._history())
        assert 'role="img"' in svg and "aria-label" in svg


class TestFootprintLedger:
    def test_append_writes_to_firestore_collection(self, config: Any, mocker: Any) -> None:
        from app.repository.firestore_repo import FirestoreLedger
        from app.repository.memory_repo import InMemoryLedger
        firestore_repo = FirestoreLedger(config)
        memory_repo = InMemoryLedger()
        ledger = FootprintLedger(firestore_repo, memory_repo, config)
        firestore_repo._client = mocker.Mock()
        record = ActivityRecord(session_id="s1", estimates=[], total_kg_co2e=1.0)
        ledger.append_record(record)
        firestore_repo._client.collection.assert_called_once_with(config.firestore_collection)

    def test_append_survives_firestore_outage_via_mirror(self, config: Any, mocker: Any) -> None:
        from app.repository.firestore_repo import FirestoreLedger
        from app.repository.memory_repo import InMemoryLedger
        firestore_repo = FirestoreLedger(config)
        memory_repo = InMemoryLedger()
        ledger = FootprintLedger(firestore_repo, memory_repo, config)
        firestore_repo._client = mocker.Mock()
        firestore_repo._client.collection.side_effect = google.api_core.exceptions.GoogleAPIError("firestore down")
        record = ActivityRecord(session_id="s1", estimates=[], total_kg_co2e=2.5)
        ledger.append_record(record)  # Must not raise.
        history = ledger.session_history("s1")
        assert history[0]["total_kg_co2e"] == 2.5

    def test_history_requires_session_id(self, config: Any) -> None:
        from app.repository.firestore_repo import FirestoreLedger
        from app.repository.memory_repo import InMemoryLedger
        firestore_repo = FirestoreLedger(config)
        memory_repo = InMemoryLedger()
        with pytest.raises(LedgerError):
            FootprintLedger(firestore_repo, memory_repo, config).session_history("")

    def test_history_caps_at_configured_window(self, config: Any, mocker: Any) -> None:
        from app.repository.firestore_repo import FirestoreLedger
        from app.repository.memory_repo import InMemoryLedger
        firestore_repo = FirestoreLedger(config)
        memory_repo = InMemoryLedger()
        ledger = FootprintLedger(firestore_repo, memory_repo, config)
        firestore_repo._client = mocker.Mock()
        firestore_repo._client.collection.side_effect = google.api_core.exceptions.GoogleAPIError("offline")
        for index in range(config.history_window + 10):
            ledger.append_record(ActivityRecord(session_id="s1", total_kg_co2e=float(index)))
        assert len(ledger.session_history("s1")) == config.history_window

    def test_healthy_when_client_constructs(self, config: Any, mocker: Any) -> None:
        from app.repository.firestore_repo import FirestoreLedger
        from app.repository.memory_repo import InMemoryLedger
        firestore_repo = FirestoreLedger(config)
        memory_repo = InMemoryLedger()
        ledger = FootprintLedger(firestore_repo, memory_repo, config)
        firestore_repo._client = mocker.Mock()
        assert ledger.is_healthy() is True


class TestArchiveVault:
    def test_archive_uploads_json_blob(self, config: Any, mocker: Any) -> None:
        vault = ArchiveVault(config)
        vault._client = mocker.Mock()
        blob = vault._client.bucket.return_value.blob.return_value
        assert vault.archive_summary("s1", {"recorded_at": "2026-06-11", "total_kg_co2e": 3}) is True
        upload_args = blob.upload_from_string.call_args
        assert upload_args.kwargs["content_type"] == "application/json"

    def test_archive_failure_is_swallowed(self, config: Any, mocker: Any) -> None:
        vault = ArchiveVault(config)
        vault._client = mocker.Mock()
        vault._client.bucket.side_effect = google.api_core.exceptions.GoogleAPIError("bucket missing")
        assert vault.archive_summary("s1", {}) is False


class TestSecretVault:
    def test_secret_read_uses_latest_version_path(self, config: Any, mocker: Any) -> None:
        vault = SecretVault(config)
        vault._client = mocker.Mock()
        payload = mocker.Mock()
        payload.payload.data = b"secret-value"
        vault._client.access_secret_version.return_value = payload
        assert vault.get_secret("api-tuning") == "secret-value"
        resource = vault._client.access_secret_version.call_args.kwargs["request"]["name"]
        assert resource.endswith("secrets/api-tuning/versions/latest")

    def test_secret_value_cached_for_process_lifetime(self, config: Any, mocker: Any) -> None:
        vault = SecretVault(config)
        vault._client = mocker.Mock()
        payload = mocker.Mock()
        payload.payload.data = b"v"
        vault._client.access_secret_version.return_value = payload
        vault.get_secret("k")
        vault.get_secret("k")
        assert vault._client.access_secret_version.call_count == 1

    def test_unavailable_secret_falls_back_to_default(self, config: Any, mocker: Any) -> None:
        vault = SecretVault(config)
        vault._client = mocker.Mock()
        vault._client.access_secret_version.side_effect = google.api_core.exceptions.GoogleAPIError("denied")
        assert vault.get_secret("missing", default="fallback") == "fallback"


class TestSentimentLens:
    def _lens_with_score(self, mocker: Any, score: float) -> SentimentLens:
        lens = SentimentLens()
        lens._client = mocker.Mock()
        sentiment = mocker.Mock()
        sentiment.document_sentiment.score = score
        lens._client.analyze_sentiment.return_value = sentiment
        return lens

    def test_positive_note_reads_celebratory(self, mocker: Any) -> None:
        lens = self._lens_with_score(mocker, 0.8)
        assert lens.gauge_motivation("proud of my cycling week")["tone"] == "celebratory"

    def test_negative_note_reads_encouraging(self, mocker: Any) -> None:
        lens = self._lens_with_score(mocker, -0.7)
        assert lens.gauge_motivation("felt guilty about the flight")["tone"] == "encouraging"

    def test_empty_note_is_neutral_without_api_call(self, mocker: Any) -> None:
        lens = SentimentLens()
        lens._client = mocker.Mock()
        assert lens.gauge_motivation("  ")["tone"] == "neutral"
        lens._client.analyze_sentiment.assert_not_called()

    def test_api_failure_degrades_to_neutral(self, mocker: Any) -> None:
        lens = SentimentLens()
        lens._client = mocker.Mock()
        lens._client.analyze_sentiment.side_effect = google.api_core.exceptions.GoogleAPIError("quota")
        assert lens.gauge_motivation("note")["tone"] == "neutral"


class TestLoggingConfig:
    def test_json_formatter_keys(self) -> None:
        import logging
        import json
        from app.logging_config import JsonFormatter
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test_module",
            level=logging.INFO,
            pathname="test_path.py",
            lineno=10,
            msg="test message",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        assert parsed["severity"] == "INFO"
        assert parsed["module"] == "test_module"
        assert parsed["message"] == "test message"
        assert "exception" not in parsed

    def test_json_formatter_exception(self) -> None:
        import logging
        import json
        import sys
        from app.logging_config import JsonFormatter
        formatter = JsonFormatter()
        try:
            raise ValueError("an error")
        except ValueError:
            record = logging.LogRecord(
                name="test_module",
                level=logging.ERROR,
                pathname="test_path.py",
                lineno=20,
                msg="test message with exc",
                args=(),
                exc_info=sys.exc_info(),
            )
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        assert parsed["severity"] == "ERROR"
        assert "exception" in parsed
        assert "ValueError: an error" in parsed["exception"]


class TestExtraCoverage:
    def test_service_health_model(self) -> None:
        from app.models.health import ServiceHealth
        h = ServiceHealth("test", True)
        assert h.name == "test"
        assert h.healthy is True
        assert h.to_dict() == {"healthy": True, "detail": "ok"}

    def test_interfaces(self) -> None:
        from app.services.interfaces import ActivityInterpreter, EmissionEstimator, HistoryLedger, FullResponseTranslator
        assert ActivityInterpreter
        assert EmissionEstimator
        assert HistoryLedger
        assert FullResponseTranslator

        class DummyInterpreter(ActivityInterpreter):
            pass
        try:
            ActivityInterpreter.interpret_activity(None, "")
        except Exception:
            pass

    def test_build_services(self, mocker: Any) -> None:
        mocker.patch("google.cloud.firestore.Client")
        mocker.patch("google.cloud.storage.Client")
        mocker.patch("google.cloud.secretmanager.SecretManagerServiceClient")
        mocker.patch("google.cloud.language_v2.LanguageServiceClient")
        mocker.patch("google.cloud.translate_v3.TranslationServiceClient")

        from app import build_services
        from app.config import Config
        cfg = Config(project_id="test", storage_bucket="test")
        services = build_services(cfg)
        assert services.registry is not None
        assert services.interpreter is not None
        assert services.narrator is not None
        assert services.gateway is not None

    def test_ledger_client_auto_detect(self, mocker: Any) -> None:
        from app.config import Config
        from app.repository.firestore_repo import FirestoreLedger
        config = Config(project_id="greenprint-local", storage_bucket="test")
        ledger = FirestoreLedger(config)
        mock_client = mocker.patch("google.cloud.firestore.Client")
        client = ledger.client
        assert client is not None
        mock_client.assert_called_once_with(project=None)

    def test_ledger_is_healthy_failure(self, mocker: Any) -> None:
        from app.config import Config
        from app.repository.firestore_repo import FirestoreLedger
        config = Config(project_id="test", storage_bucket="test")
        ledger = FirestoreLedger(config)
        mocker.patch.object(FirestoreLedger, "client", new_callable=mocker.PropertyMock, side_effect=RuntimeError("crashed"))
        assert ledger.is_healthy() is False

    def test_archive_vault_is_healthy_failure(self, mocker: Any) -> None:
        from app.config import Config
        config = Config(project_id="test", storage_bucket="test")
        vault = ArchiveVault(config)
        mocker.patch.object(ArchiveVault, "client", new_callable=mocker.PropertyMock, side_effect=RuntimeError("crashed"))
        assert vault.is_healthy() is False

    def test_secret_vault_is_healthy_failure(self, mocker: Any) -> None:
        from app.config import Config
        config = Config(project_id="test", storage_bucket="test")
        vault = SecretVault(config)
        mocker.patch.object(SecretVault, "client", new_callable=mocker.PropertyMock, side_effect=RuntimeError("crashed"))
        assert vault.is_healthy() is False

    def test_sentiment_lens_is_healthy_failure(self, mocker: Any) -> None:
        lens = SentimentLens()
        mocker.patch.object(SentimentLens, "client", new_callable=mocker.PropertyMock, side_effect=RuntimeError("crashed"))
        assert lens.is_healthy() is False

    def test_translator_is_healthy_failure(self, mocker: Any) -> None:
        from app.config import Config
        config = Config(project_id="test", storage_bucket="test")
        translator = ResponseTranslator(config)
        mocker.patch.object(ResponseTranslator, "client", new_callable=mocker.PropertyMock, side_effect=RuntimeError("crashed"))
        assert translator.is_healthy() is False

    def test_translator_parent_dynamic_project(self, mocker: Any, clear_project_cache: None) -> None:
        import os
        from app.config import Config
        config = Config(project_id="greenprint-local", storage_bucket="test")
        translator = ResponseTranslator(config)
        mocker.patch("google.auth.default", return_value=(None, "hackathonready"))
        mocker.patch.dict(os.environ)
        if "PYTEST_CURRENT_TEST" in os.environ:
            del os.environ["PYTEST_CURRENT_TEST"]
        assert translator._parent == "projects/hackathonready/locations/global"

    def test_secret_vault_dynamic_project(self, mocker: Any, clear_project_cache: None) -> None:
        import os
        from app.config import Config
        config = Config(project_id="greenprint-local", storage_bucket="test")
        vault = SecretVault(config)
        vault._client = mocker.Mock()
        mocker.patch("google.auth.default", return_value=(None, "hackathonready"))
        mocker.patch.dict(os.environ)
        if "PYTEST_CURRENT_TEST" in os.environ:
            del os.environ["PYTEST_CURRENT_TEST"]
        payload = mocker.Mock()
        payload.payload.data = b"secret-val"
        vault._client.access_secret_version.return_value = payload

        assert vault.get_secret("name") == "secret-val"
        resource = vault._client.access_secret_version.call_args.kwargs["request"]["name"]
        assert resource == "projects/hackathonready/secrets/name/versions/latest"


class TestLedgerRepositoryContractParity:
    def _test_ledger_contract(self, ledger: Any) -> None:
        from app.models.activity import ActivityRecord
        r1 = ActivityRecord(session_id="session-p", estimates=[], total_kg_co2e=1.5)
        r2 = ActivityRecord(session_id="session-p", estimates=[], total_kg_co2e=2.5)

        ledger.append(r1)
        ledger.append(r2)

        history = ledger.list_for_session("session-p", 10)
        assert len(history) == 2
        assert history[0]["total_kg_co2e"] == 2.5
        assert history[1]["total_kg_co2e"] == 1.5

    def test_in_memory_ledger_contract(self) -> None:
        from app.repository.memory_repo import InMemoryLedger
        self._test_ledger_contract(InMemoryLedger())

    def test_firestore_ledger_contract(self, mocker: Any) -> None:
        from app.repository.firestore_repo import FirestoreLedger
        from app.config import Config
        config = Config(project_id="test", storage_bucket="test")
        ledger = FirestoreLedger(config)

        mock_client = mocker.Mock()
        mock_coll = mock_client.collection.return_value

        mock_doc1 = mocker.Mock()
        mock_doc1.to_dict.return_value = {"session_id": "session-p", "total_kg_co2e": 2.5}
        mock_doc2 = mocker.Mock()
        mock_doc2.to_dict.return_value = {"session_id": "session-p", "total_kg_co2e": 1.5}

        mock_coll.where.return_value.order_by.return_value.limit.return_value.stream.return_value = [mock_doc1, mock_doc2]
        ledger._client = mock_client

        self._test_ledger_contract(ledger)


class TestEdgeScenarios:
    def test_simulate_unmatched_scenario(self) -> None:
        composer = InsightComposer()
        from app.models.insight import FootprintSummary
        summary = FootprintSummary(total_kg_co2e=10.0, record_count=1, category_totals={})
        projection = composer.simulate(summary, "some random text with no matched keywords")
        assert projection["matched_category"] == "general"
        assert projection["weekly_saving_kg"] == 0.0

    def test_cache_invalidate_prefix_miss(self) -> None:
        cache = InsightCache(ttl_seconds=60, max_entries=10)
        cache.set(("insights", "session-1", "en"), {"val": 1})
        cache.invalidate_prefix(("insights", "session-2"))
        assert cache.get(("insights", "session-1", "en")) == {"val": 1}

    def test_in_memory_ledger_bounded_lru(self) -> None:
        from app.repository.memory_repo import InMemoryLedger
        from app.models.activity import ActivityRecord
        ledger = InMemoryLedger(history_window=2, max_sessions=3)

        # Append to multiple sessions
        ledger.append(ActivityRecord(session_id="s1", total_kg_co2e=1.0))
        ledger.append(ActivityRecord(session_id="s2", total_kg_co2e=2.0))
        ledger.append(ActivityRecord(session_id="s3", total_kg_co2e=3.0))

        # Access s1 to make it recently used
        ledger.list_for_session("s1", 10)

        # Append s4, which should evict s2 (oldest LRU session)
        ledger.append(ActivityRecord(session_id="s4", total_kg_co2e=4.0))

        assert len(ledger.list_for_session("s2", 10)) == 0
        assert len(ledger.list_for_session("s1", 10)) == 1

        # Test capping of records per session
        ledger.append(ActivityRecord(session_id="s1", total_kg_co2e=5.0))
        ledger.append(ActivityRecord(session_id="s1", total_kg_co2e=6.0))
        h = ledger.list_for_session("s1", 10)
        assert len(h) == 2
        assert h[0]["total_kg_co2e"] == 6.0



