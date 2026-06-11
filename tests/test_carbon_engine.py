"""CarbonIntelligenceEngine: model-output parsing and heuristic fallback."""
from __future__ import annotations

from typing import Any
import pytest
import google.api_core.exceptions

from app.config import load_config, Config
from app.exceptions import EstimationError
from app.services.carbon_engine import CarbonIntelligenceEngine
from app.services.emission_registry import EmissionFactorRegistry


@pytest.fixture()
def engine() -> CarbonIntelligenceEngine:
    return CarbonIntelligenceEngine(load_config(), EmissionFactorRegistry())


class TestModelJsonParsing:
    def test_parses_clean_json_array(self, engine: CarbonIntelligenceEngine) -> None:
        raw = '[{"factor_key": "transport.metro_km", "quantity": 8, "note": "commute", "confidence": 0.95}]'
        items = engine._parse_model_json(raw)
        assert items[0].factor_key == "transport.metro_km"
        assert items[0].quantity == 8.0

    def test_parses_json_inside_markdown_fences(self, engine: CarbonIntelligenceEngine) -> None:
        raw = '```json\n[{"factor_key": "food.meal_veg", "quantity": 1}]\n```'
        items = engine._parse_model_json(raw)
        assert items[0].factor_key == "food.meal_veg"

    def test_skips_entries_missing_factor_key(self, engine: CarbonIntelligenceEngine) -> None:
        raw = '[{"quantity": 3}, {"factor_key": "transport.bus_km", "quantity": 5}]'
        items = engine._parse_model_json(raw)
        assert len(items) == 1

    def test_non_json_raises_estimation_error(self, engine: CarbonIntelligenceEngine) -> None:
        with pytest.raises(EstimationError):
            engine._parse_model_json("I could not understand the request.")

    def test_empty_array_raises_estimation_error(self, engine: CarbonIntelligenceEngine) -> None:
        with pytest.raises(EstimationError):
            engine._parse_model_json("[]")


class TestHeuristicFallback:
    def test_recognises_car_with_stated_distance(self, engine: CarbonIntelligenceEngine) -> None:
        items = engine._heuristic_parse("drove 12 km to office")
        assert items[0].factor_key == "transport.car_petrol_km"
        assert items[0].quantity == 12.0

    def test_recognises_multiple_activities(self, engine: CarbonIntelligenceEngine) -> None:
        items = engine._heuristic_parse("took the metro and had chicken biryani")
        keys = {item.factor_key for item in items}
        assert "transport.metro_km" in keys
        assert "food.meal_nonveg" in keys

    def test_fallback_confidence_is_reduced(self, engine: CarbonIntelligenceEngine) -> None:
        items = engine._heuristic_parse("ran the AC all evening")
        assert all(item.confidence == 0.5 for item in items)

    def test_unrecognisable_text_raises(self, engine: CarbonIntelligenceEngine) -> None:
        with pytest.raises(EstimationError):
            engine._heuristic_parse("zzz qqq xyzzy")

    def test_empty_text_raises_before_model_call(self, engine: CarbonIntelligenceEngine) -> None:
        with pytest.raises(EstimationError):
            engine.interpret_activity("   ")


class TestNarrativeFallbacks:
    def test_fallback_tip_targets_largest_category(self, engine: CarbonIntelligenceEngine) -> None:
        from app.models.activity import EmissionEstimate
        estimates = [
            EmissionEstimate("transport.car_petrol_km", "Petrol car travel", "transport", 10.0, "km", 1.8, 1.0),
            EmissionEstimate("food.meal_veg", "Vegetarian meal", "food", 1.0, "meals", 0.7, 1.0),
        ]
        tip = engine._fallback_tip(estimates)
        assert "metro" in tip or "car" in tip

    def test_fallback_tip_for_empty_estimates(self, engine: CarbonIntelligenceEngine) -> None:
        assert "awareness" in engine._fallback_tip([]).lower()


class TestGenerativeModelPaths:
    def test_interpret_with_gemini_success(self, mocker: Any, engine: CarbonIntelligenceEngine) -> None:
        mock_model = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = '[{"factor_key": "transport.metro_km", "quantity": 10.0, "note": "commute", "confidence": 1.0}]'
        mock_model.generate_content.return_value = mock_response
        mocker.patch.object(engine, "_ensure_model", return_value=mock_model)

        items = engine.interpret_activity("took the metro")
        assert len(items) == 1
        assert items[0].factor_key == "transport.metro_km"
        assert items[0].quantity == 10.0

    def test_interpret_with_gemini_garbage_fallback(self, mocker: Any, engine: CarbonIntelligenceEngine) -> None:
        mock_model = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = 'this is garbage, not json'
        mock_model.generate_content.return_value = mock_response
        mocker.patch.object(engine, "_ensure_model", return_value=mock_model)

        # Should fallback to heuristic parse and succeed
        items = engine.interpret_activity("drove 12 km to office")
        assert len(items) == 1
        assert items[0].factor_key == "transport.car_petrol_km"
        assert items[0].quantity == 12.0

    def test_draft_eco_tip_gemini_success(self, mocker: Any, engine: CarbonIntelligenceEngine) -> None:
        from app.models.activity import EmissionEstimate
        mock_model = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = "Try walking or cycling for short trips!"
        mock_model.generate_content.return_value = mock_response
        mocker.patch.object(engine, "_ensure_model", return_value=mock_model)

        estimates = [
            EmissionEstimate("transport.car_petrol_km", "Petrol car travel", "transport", 10.0, "km", 1.8, 1.0)
        ]
        tip = engine.draft_eco_tip(estimates, 1.8)
        assert tip == "Try walking or cycling for short trips!"

    def test_draft_simulation_narrative_gemini_success(self, mocker: Any, engine: CarbonIntelligenceEngine) -> None:
        mock_model = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = "Encouraging narrative"
        mock_model.generate_content.return_value = mock_response
        mocker.patch.object(engine, "_ensure_model", return_value=mock_model)

        narrative = engine.draft_simulation_narrative("commute", 5.0)
        assert narrative == "Encouraging narrative"


class TestCarbonEngineCoverage:
    def test_ensure_model_dynamic_auth(self, mocker: Any) -> None:
        mock_v_init = mocker.patch("vertexai.init")
        mock_a_init = mocker.patch("google.cloud.aiplatform.init")
        mocker.patch("vertexai.generative_models.GenerativeModel")
        mocker.patch("google.auth.default", return_value=(None, "hackathonready"))

        cfg = Config(project_id="greenprint-local", storage_bucket="test-bucket")
        local_engine = CarbonIntelligenceEngine(cfg, EmissionFactorRegistry())

        model = local_engine._ensure_model()
        assert model is not None
        mock_v_init.assert_called_once_with(project="hackathonready", location="asia-south1")

    def test_draft_eco_tip_upstream_failure(self, mocker: Any, engine: CarbonIntelligenceEngine) -> None:
        from app.models.activity import EmissionEstimate
        mocker.patch.object(engine, "_ensure_model", side_effect=google.api_core.exceptions.GoogleAPIError("Vertex down"))
        estimates = [
            EmissionEstimate("transport.car_petrol_km", "Petrol car travel", "transport", 10.0, "km", 1.8, 1.0)
        ]
        tip = engine.draft_eco_tip(estimates, 1.8)
        assert "metro" in tip or "car" in tip

    def test_draft_simulation_narrative_upstream_failure(self, mocker: Any, engine: CarbonIntelligenceEngine) -> None:
        mocker.patch.object(engine, "_ensure_model", side_effect=google.api_core.exceptions.GoogleAPIError("Vertex down"))
        narrative = engine.draft_simulation_narrative("commute", 5.0)
        assert "saves about 5.0" in narrative

    def test_is_healthy_failure(self, mocker: Any, engine: CarbonIntelligenceEngine) -> None:
        mocker.patch.object(engine, "_ensure_model", side_effect=RuntimeError("crashed"))
        assert engine.is_healthy() is False
