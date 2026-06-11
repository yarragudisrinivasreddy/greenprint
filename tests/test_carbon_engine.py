"""Tests for ActivityInterpreter, NarrativeComposer, and VertexGateway."""
from __future__ import annotations

import json
from typing import Any
import pytest
import google.api_core.exceptions
import google.auth.exceptions

from app.config import load_config, Config
from app.exceptions import EstimationError
from app.services.activity_interpreter import ActivityInterpreter
from app.services.narrative_composer import NarrativeComposer
from app.services.vertex_gateway import VertexGateway
from app.services.emission_registry import EmissionFactorRegistry


@pytest.fixture()
def config() -> Config:
    return load_config()


@pytest.fixture()
def gateway(config: Config) -> VertexGateway:
    return VertexGateway(config)


@pytest.fixture()
def registry() -> EmissionFactorRegistry:
    return EmissionFactorRegistry()


@pytest.fixture()
def interpreter(gateway: VertexGateway, registry: EmissionFactorRegistry) -> ActivityInterpreter:
    return ActivityInterpreter(gateway, registry)


@pytest.fixture()
def composer(gateway: VertexGateway) -> NarrativeComposer:
    return NarrativeComposer(gateway)


class TestModelJsonParsing:
    def test_parses_clean_json_array(self, interpreter: ActivityInterpreter) -> None:
        raw = '[{"factor_key": "transport.metro_km", "quantity": 8, "note": "commute", "confidence": 0.95}]'
        items = interpreter._parse_model_json(raw)
        assert items[0].factor_key == "transport.metro_km"
        assert items[0].quantity == 8.0

    def test_parses_json_inside_markdown_fences(self, interpreter: ActivityInterpreter) -> None:
        raw = '```json\n[{"factor_key": "food.meal_veg", "quantity": 1}]\n```'
        items = interpreter._parse_model_json(raw)
        assert items[0].factor_key == "food.meal_veg"

    def test_skips_entries_missing_factor_key(self, interpreter: ActivityInterpreter) -> None:
        raw = '[{"quantity": 3}, {"factor_key": "transport.bus_km", "quantity": 5}]'
        items = interpreter._parse_model_json(raw)
        assert len(items) == 1

    def test_non_json_raises_estimation_error(self, interpreter: ActivityInterpreter) -> None:
        with pytest.raises(EstimationError):
            interpreter._parse_model_json("I could not understand the request.")

    def test_empty_array_raises_estimation_error(self, interpreter: ActivityInterpreter) -> None:
        with pytest.raises(EstimationError):
            interpreter._parse_model_json("[]")


class TestHeuristicFallback:
    def test_recognises_car_with_stated_distance(self, interpreter: ActivityInterpreter) -> None:
        items = interpreter._heuristic_parse("drove 12 km to office")
        assert items[0].factor_key == "transport.car_petrol_km"
        assert items[0].quantity == 12.0

    def test_recognises_multiple_activities(self, interpreter: ActivityInterpreter) -> None:
        items = interpreter._heuristic_parse("took the metro and had chicken biryani")
        keys = {item.factor_key for item in items}
        assert "transport.metro_km" in keys
        assert "food.meal_nonveg" in keys

    def test_fallback_confidence_is_reduced(self, interpreter: ActivityInterpreter) -> None:
        items = interpreter._heuristic_parse("ran the AC all evening")
        assert all(item.confidence == 0.5 for item in items)

    def test_unrecognisable_text_raises(self, interpreter: ActivityInterpreter) -> None:
        with pytest.raises(EstimationError):
            interpreter._heuristic_parse("zzz qqq xyzzy")

    def test_empty_text_raises_before_model_call(self, interpreter: ActivityInterpreter) -> None:
        with pytest.raises(EstimationError):
            interpreter.interpret_activity("   ")


class TestNarrativeFallbacks:
    def test_fallback_tip_targets_largest_category(self, composer: NarrativeComposer) -> None:
        from app.models.activity import EmissionEstimate
        estimates = [
            EmissionEstimate("transport.car_petrol_km", "Petrol car travel", "transport", 10.0, "km", 1.8, 1.0),
            EmissionEstimate("food.meal_veg", "Vegetarian meal", "food", 1.0, "meals", 0.7, 1.0),
        ]
        tip = composer._fallback_tip(estimates)
        assert "metro" in tip or "car" in tip

    def test_fallback_tip_for_empty_estimates(self, composer: NarrativeComposer) -> None:
        assert "awareness" in composer._fallback_tip([]).lower()


class TestGenerativeModelPaths:
    def test_interpret_with_gemini_success(self, mocker: Any, interpreter: ActivityInterpreter) -> None:
        mock_model = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = '[{"factor_key": "transport.metro_km", "quantity": 10.0, "note": "commute", "confidence": 1.0}]'
        mock_model.generate_content.return_value = mock_response
        mocker.patch.object(interpreter._gateway, "get_model", return_value=mock_model)

        items = interpreter.interpret_activity("took the metro")
        assert len(items) == 1
        assert items[0].factor_key == "transport.metro_km"
        assert items[0].quantity == 10.0

    def test_interpret_with_gemini_garbage_fallback(self, mocker: Any, interpreter: ActivityInterpreter) -> None:
        mock_model = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = 'this is garbage, not json'
        mock_model.generate_content.return_value = mock_response
        mocker.patch.object(interpreter._gateway, "get_model", return_value=mock_model)

        # Should fallback to heuristic parse and succeed
        items = interpreter.interpret_activity("drove 12 km to office")
        assert len(items) == 1
        assert items[0].factor_key == "transport.car_petrol_km"
        assert items[0].quantity == 12.0

    def test_draft_eco_tip_gemini_success(self, mocker: Any, composer: NarrativeComposer) -> None:
        from app.models.activity import EmissionEstimate
        mock_model = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = "Try walking or cycling for short trips!"
        mock_model.generate_content.return_value = mock_response
        mocker.patch.object(composer._gateway, "get_model", return_value=mock_model)

        estimates = [
            EmissionEstimate("transport.car_petrol_km", "Petrol car travel", "transport", 10.0, "km", 1.8, 1.0)
        ]
        tip = composer.draft_eco_tip(estimates, 1.8)
        assert tip == "Try walking or cycling for short trips!"

    def test_draft_simulation_narrative_gemini_success(self, mocker: Any, composer: NarrativeComposer) -> None:
        mock_model = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = "Encouraging narrative"
        mock_model.generate_content.return_value = mock_response
        mocker.patch.object(composer._gateway, "get_model", return_value=mock_model)

        narrative = composer.draft_simulation_narrative("commute", 5.0)
        assert narrative == "Encouraging narrative"


class TestVertexGatewayCoverage:
    def test_get_model_dynamic_auth(self, mocker: Any) -> None:
        mock_v_init = mocker.patch("app.services.vertex_gateway.vertexai.init")
        mock_a_init = mocker.patch("app.services.vertex_gateway.aiplatform.init")
        mocker.patch("app.services.vertex_gateway.GenerativeModel")
        mocker.patch("app.services.vertex_gateway.resolve_project_id", return_value="hackathonready")

        cfg = Config(project_id="greenprint-local", storage_bucket="test-bucket")
        local_gateway = VertexGateway(cfg)

        model = local_gateway.get_model()
        assert model is not None
        mock_v_init.assert_called_once_with(project="hackathonready", location="asia-south1")

    def test_draft_eco_tip_upstream_failure(self, mocker: Any, composer: NarrativeComposer) -> None:
        from app.models.activity import EmissionEstimate
        mocker.patch.object(composer._gateway, "get_model", side_effect=google.api_core.exceptions.GoogleAPIError("Vertex down"))
        estimates = [
            EmissionEstimate("transport.car_petrol_km", "Petrol car travel", "transport", 10.0, "km", 1.8, 1.0)
        ]
        tip = composer.draft_eco_tip(estimates, 1.8)
        assert "metro" in tip or "car" in tip

    def test_draft_simulation_narrative_upstream_failure(self, mocker: Any, composer: NarrativeComposer) -> None:
        mocker.patch.object(composer._gateway, "get_model", side_effect=google.api_core.exceptions.GoogleAPIError("Vertex down"))
        narrative = composer.draft_simulation_narrative("commute", 5.0)
        assert "saves about 5.0" in narrative

    def test_gateway_is_healthy_failure(self, mocker: Any, gateway: VertexGateway) -> None:
        mocker.patch.object(gateway, "get_model", side_effect=RuntimeError("crashed"))
        assert gateway.is_healthy() is False
