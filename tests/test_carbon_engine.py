"""CarbonIntelligenceEngine: model-output parsing and heuristic fallback."""
import pytest

from app.config import load_config
from app.exceptions import EstimationError
from app.services.carbon_engine import CarbonIntelligenceEngine
from app.services.emission_registry import EmissionFactorRegistry


@pytest.fixture()
def engine():
    return CarbonIntelligenceEngine(load_config(), EmissionFactorRegistry())


class TestModelJsonParsing:
    def test_parses_clean_json_array(self, engine):
        raw = '[{"factor_key": "transport.metro_km", "quantity": 8, "note": "commute", "confidence": 0.95}]'
        items = engine._parse_model_json(raw)
        assert items[0].factor_key == "transport.metro_km"
        assert items[0].quantity == 8.0

    def test_parses_json_inside_markdown_fences(self, engine):
        raw = '```json\n[{"factor_key": "food.meal_veg", "quantity": 1}]\n```'
        items = engine._parse_model_json(raw)
        assert items[0].factor_key == "food.meal_veg"

    def test_skips_entries_missing_factor_key(self, engine):
        raw = '[{"quantity": 3}, {"factor_key": "transport.bus_km", "quantity": 5}]'
        items = engine._parse_model_json(raw)
        assert len(items) == 1

    def test_non_json_raises_estimation_error(self, engine):
        with pytest.raises(EstimationError):
            engine._parse_model_json("I could not understand the request.")

    def test_empty_array_raises_estimation_error(self, engine):
        with pytest.raises(EstimationError):
            engine._parse_model_json("[]")


class TestHeuristicFallback:
    def test_recognises_car_with_stated_distance(self, engine):
        items = engine._heuristic_parse("drove 12 km to office")
        assert items[0].factor_key == "transport.car_petrol_km"
        assert items[0].quantity == 12.0

    def test_recognises_multiple_activities(self, engine):
        items = engine._heuristic_parse("took the metro and had chicken biryani")
        keys = {item.factor_key for item in items}
        assert "transport.metro_km" in keys
        assert "food.meal_nonveg" in keys

    def test_fallback_confidence_is_reduced(self, engine):
        items = engine._heuristic_parse("ran the AC all evening")
        assert all(item.confidence == 0.5 for item in items)

    def test_unrecognisable_text_raises(self, engine):
        with pytest.raises(EstimationError):
            engine._heuristic_parse("zzz qqq xyzzy")

    def test_empty_text_raises_before_model_call(self, engine):
        with pytest.raises(EstimationError):
            engine.interpret_activity("   ")


class TestNarrativeFallbacks:
    def test_fallback_tip_targets_largest_category(self, engine):
        from app.models.activity import EmissionEstimate
        estimates = [
            EmissionEstimate("transport.car_petrol_km", "Petrol car travel", "transport", 10, "km", 1.8, 1.0),
            EmissionEstimate("food.meal_veg", "Vegetarian meal", "food", 1, "meals", 0.7, 1.0),
        ]
        tip = engine._fallback_tip(estimates)
        assert "metro" in tip or "car" in tip

    def test_fallback_tip_for_empty_estimates(self, engine):
        assert "awareness" in engine._fallback_tip([]).lower()
