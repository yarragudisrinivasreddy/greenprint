"""Deterministic math contract of the EmissionFactorRegistry."""
import pytest

from app.exceptions import EstimationError
from app.models.activity import ActivityItem
from app.services.emission_registry import EmissionFactorRegistry


@pytest.fixture()
def registry():
    return EmissionFactorRegistry()


class TestFactorResolution:
    def test_known_key_resolves_to_itself(self, registry):
        assert registry.resolve_factor_key("transport.metro_km") == "transport.metro_km"

    def test_alias_resolves_to_canonical_key(self, registry):
        assert registry.resolve_factor_key("transport.car_km") == "transport.car_petrol_km"

    def test_resolution_is_case_insensitive(self, registry):
        assert registry.resolve_factor_key("Transport.Metro_KM") == "transport.metro_km"

    def test_unknown_key_raises_estimation_error(self, registry):
        with pytest.raises(EstimationError):
            registry.resolve_factor_key("transport.teleport_km")

    def test_empty_key_raises_estimation_error(self, registry):
        with pytest.raises(EstimationError):
            registry.resolve_factor_key("")


class TestEstimateMath:
    def test_petrol_car_estimate_exact(self, registry):
        estimate = registry.estimate(ActivityItem("transport.car_petrol_km", 12))
        assert estimate.emission_kg_co2e == pytest.approx(2.16)

    def test_metro_estimate_exact(self, registry):
        estimate = registry.estimate(ActivityItem("transport.metro_km", 10))
        assert estimate.emission_kg_co2e == pytest.approx(0.15)

    def test_grid_electricity_uses_india_intensity(self, registry):
        estimate = registry.estimate(ActivityItem("energy.grid_kwh_in", 4))
        assert estimate.emission_kg_co2e == pytest.approx(2.84)

    def test_zero_emission_factor_for_cycling(self, registry):
        estimate = registry.estimate(ActivityItem("transport.cycle_km", 15))
        assert estimate.emission_kg_co2e == 0.0

    def test_zero_quantity_is_valid_and_zero(self, registry):
        estimate = registry.estimate(ActivityItem("food.meal_veg", 0))
        assert estimate.emission_kg_co2e == 0.0

    def test_negative_quantity_rejected(self, registry):
        with pytest.raises(EstimationError):
            registry.estimate(ActivityItem("food.meal_veg", -1))

    def test_none_quantity_rejected(self, registry):
        with pytest.raises(EstimationError):
            registry.estimate(ActivityItem("food.meal_veg", None))

    def test_estimate_carries_unit_and_category(self, registry):
        estimate = registry.estimate(ActivityItem("food.meal_nonveg", 1))
        assert estimate.unit == "meals"
        assert estimate.category == "food"


class TestBatchEstimation:
    def test_batch_totals_sum_of_items(self, registry):
        items = [
            ActivityItem("transport.car_petrol_km", 10),  # 1.8
            ActivityItem("food.meal_nonveg", 1),          # 2.0
        ]
        estimates, total = registry.estimate_batch(items)
        assert len(estimates) == 2
        assert total == pytest.approx(3.8)

    def test_batch_skips_unknown_factor_without_failing(self, registry):
        items = [
            ActivityItem("transport.car_petrol_km", 10),
            ActivityItem("nonsense.key", 5),
        ]
        estimates, total = registry.estimate_batch(items)
        assert len(estimates) == 1
        assert total == pytest.approx(1.8)

    def test_empty_batch_returns_zero_total(self, registry):
        estimates, total = registry.estimate_batch([])
        assert estimates == [] and total == 0.0


class TestCatalog:
    def test_catalog_exposes_every_factor(self, registry):
        catalog = registry.factor_catalog()
        assert set(catalog) == set(registry.FACTORS)

    def test_catalog_entries_have_unit_label_category(self, registry):
        entry = registry.factor_catalog()["transport.bus_km"]
        assert entry["unit"] == "km" and entry["category"] == "transport"

    def test_registry_reports_healthy(self, registry):
        assert registry.is_healthy() is True
