"""Service-level behaviour: translator exclusions, cache, composer, ledger mirror, and Google-backed wrapper resilient contracts."""
import time
import pytest

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
def translator(mocker):
    service = ResponseTranslator(load_config())
    fake_client = mocker.Mock()
    fake_client.translate_text.side_effect = lambda request: mocker.Mock(
        translations=[mocker.Mock(translated_text=f"hi::{request['contents'][0]}")]
    )
    service._client = fake_client
    return service


@pytest.fixture()
def config():
    return load_config()


class TestTranslatorExclusions:
    def test_english_passthrough_makes_no_calls(self, translator):
        payload = {"eco_tip": "Walk more"}
        assert translator.translate_response(payload, "en") == payload
        translator._client.translate_text.assert_not_called()

    def test_prose_values_are_translated(self, translator):
        result = translator.translate_response({"eco_tip": "Walk more"}, "hi")
        assert result["eco_tip"] == "hi::Walk more"

    def test_non_translatable_keys_skipped(self, translator):
        result = translator.translate_response({"factor_key": "transport.metro_km"}, "hi")
        assert result["factor_key"] == "transport.metro_km"

    def test_hashtags_never_translated(self, translator):
        result = translator.translate_response({"share_text": "#GreenPrint"}, "hi")
        assert result["share_text"] == "#GreenPrint"

    def test_unit_symbols_never_translated(self, translator):
        result = translator.translate_response({"unit_note": "kgCO2e"}, "hi")
        assert result["unit_note"] == "kgCO2e"

    def test_numbers_pass_through_untouched(self, translator):
        result = translator.translate_response({"total_kg_co2e": 3.8}, "hi")
        assert result["total_kg_co2e"] == 3.8

    def test_nested_lists_translated_recursively(self, translator):
        result = translator.translate_response({"actions": [{"action": "Cycle short trips"}]}, "hi")
        assert result["actions"][0]["action"] == "hi::Cycle short trips"

    def test_unsupported_language_raises(self, translator):
        with pytest.raises(TranslationError):
            translator.translate_response({"eco_tip": "x"}, "xx")


class TestInsightCache:
    def test_set_then_get_round_trip(self):
        cache = InsightCache(ttl_seconds=60, max_entries=4)
        cache.set(("insights", "s1", "en"), {"a": 1})
        assert cache.get(("insights", "s1", "en")) == {"a": 1}

    def test_expired_entry_returns_none(self):
        cache = InsightCache(ttl_seconds=0, max_entries=4)
        cache.set(("k",), "v")
        time.sleep(0.01)
        assert cache.get(("k",)) is None

    def test_lru_eviction_on_overflow(self):
        cache = InsightCache(ttl_seconds=60, max_entries=2)
        cache.set(("a",), 1)
        cache.set(("b",), 2)
        cache.set(("c",), 3)
        assert cache.get(("a",)) is None
        assert cache.get(("c",)) == 3


class TestInsightComposer:
    def _history(self):
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

    def test_summarize_aggregates_categories(self):
        summary = InsightComposer().summarize(self._history())
        assert summary.category_totals["transport"] == 1.8
        assert summary.total_kg_co2e == 3.8

    def test_eco_score_neutral_for_empty_history(self):
        score = InsightComposer().eco_score([])
        assert score["score"] == 50

    def test_eco_score_rewards_below_baseline_day(self):
        score = InsightComposer().eco_score(self._history())
        assert score["score"] > 50
        assert score["streak_days"] == 1

    def test_reduction_actions_ranked_by_saving(self):
        composer = InsightComposer()
        actions = composer.rank_reduction_actions(composer.summarize(self._history()))
        savings = [a.weekly_saving_kg for a in actions]
        assert savings == sorted(savings, reverse=True)

    def test_trend_svg_is_accessible(self):
        svg = InsightComposer().weekly_trend_svg(self._history())
        assert 'role="img"' in svg and "aria-label" in svg


class TestFootprintLedger:
    def test_append_writes_to_firestore_collection(self, config, mocker):
        ledger = FootprintLedger(config)
        ledger._client = mocker.Mock()
        record = ActivityRecord(session_id="s1", estimates=[], total_kg_co2e=1.0)
        ledger.append_record(record)
        ledger._client.collection.assert_called_once_with(config.firestore_collection)

    def test_append_survives_firestore_outage_via_mirror(self, config, mocker):
        ledger = FootprintLedger(config)
        ledger._client = mocker.Mock()
        ledger._client.collection.side_effect = RuntimeError("firestore down")
        record = ActivityRecord(session_id="s1", estimates=[], total_kg_co2e=2.5)
        ledger.append_record(record)  # Must not raise.
        history = ledger.session_history("s1")
        assert history[0]["total_kg_co2e"] == 2.5

    def test_history_requires_session_id(self, config):
        with pytest.raises(LedgerError):
            FootprintLedger(config).session_history("")

    def test_history_caps_at_configured_window(self, config, mocker):
        ledger = FootprintLedger(config)
        ledger._client = mocker.Mock()
        ledger._client.collection.side_effect = RuntimeError("offline")
        for index in range(config.history_window + 10):
            ledger.append_record(ActivityRecord(session_id="s1", total_kg_co2e=float(index)))
        assert len(ledger.session_history("s1")) == config.history_window

    def test_healthy_when_client_constructs(self, config, mocker):
        ledger = FootprintLedger(config)
        ledger._client = mocker.Mock()
        assert ledger.is_healthy() is True


class TestArchiveVault:
    def test_archive_uploads_json_blob(self, config, mocker):
        vault = ArchiveVault(config)
        vault._client = mocker.Mock()
        blob = vault._client.bucket.return_value.blob.return_value
        assert vault.archive_summary("s1", {"recorded_at": "2026-06-11", "total_kg_co2e": 3}) is True
        upload_args = blob.upload_from_string.call_args
        assert upload_args.kwargs["content_type"] == "application/json"

    def test_archive_failure_is_swallowed(self, config, mocker):
        vault = ArchiveVault(config)
        vault._client = mocker.Mock()
        vault._client.bucket.side_effect = RuntimeError("bucket missing")
        assert vault.archive_summary("s1", {}) is False


class TestSecretVault:
    def test_secret_read_uses_latest_version_path(self, config, mocker):
        vault = SecretVault(config)
        vault._client = mocker.Mock()
        payload = mocker.Mock()
        payload.payload.data = b"secret-value"
        vault._client.access_secret_version.return_value = payload
        assert vault.get_secret("api-tuning") == "secret-value"
        resource = vault._client.access_secret_version.call_args.kwargs["request"]["name"]
        assert resource.endswith("secrets/api-tuning/versions/latest")

    def test_secret_value_cached_for_process_lifetime(self, config, mocker):
        vault = SecretVault(config)
        vault._client = mocker.Mock()
        payload = mocker.Mock()
        payload.payload.data = b"v"
        vault._client.access_secret_version.return_value = payload
        vault.get_secret("k")
        vault.get_secret("k")
        assert vault._client.access_secret_version.call_count == 1

    def test_unavailable_secret_falls_back_to_default(self, config, mocker):
        vault = SecretVault(config)
        vault._client = mocker.Mock()
        vault._client.access_secret_version.side_effect = RuntimeError("denied")
        assert vault.get_secret("missing", default="fallback") == "fallback"


class TestSentimentLens:
    def _lens_with_score(self, mocker, score):
        lens = SentimentLens()
        lens._client = mocker.Mock()
        sentiment = mocker.Mock()
        sentiment.document_sentiment.score = score
        lens._client.analyze_sentiment.return_value = sentiment
        return lens

    def test_positive_note_reads_celebratory(self, mocker):
        lens = self._lens_with_score(mocker, 0.8)
        assert lens.gauge_motivation("proud of my cycling week")["tone"] == "celebratory"

    def test_negative_note_reads_encouraging(self, mocker):
        lens = self._lens_with_score(mocker, -0.7)
        assert lens.gauge_motivation("felt guilty about the flight")["tone"] == "encouraging"

    def test_empty_note_is_neutral_without_api_call(self, mocker):
        lens = SentimentLens()
        lens._client = mocker.Mock()
        assert lens.gauge_motivation("  ")["tone"] == "neutral"
        lens._client.analyze_sentiment.assert_not_called()

    def test_api_failure_degrades_to_neutral(self, mocker):
        lens = SentimentLens()
        lens._client = mocker.Mock()
        lens._client.analyze_sentiment.side_effect = RuntimeError("quota")
        assert lens.gauge_motivation("note")["tone"] == "neutral"
