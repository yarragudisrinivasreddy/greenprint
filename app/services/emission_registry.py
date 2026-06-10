"""EmissionFactorRegistry — GreenPrint's deterministic carbon calculator.

Design principle: **Gemini interprets, the registry computes.** The
language model only maps user activities to factor keys and quantities;
all kgCO2e arithmetic happens here against an auditable, India-first
factor table. Emissions are therefore reproducible and never subject to
model hallucination.

Factor sources: CEA (India grid average), IPCC lifecycle assessments and
published Indian transport/diet studies, rounded for awareness-grade
estimation (directional figures, not certified carbon accounting).
"""
from app.constants import ActivityCategory
from app.exceptions import EstimationError
from app.logging_config import get_logger
from app.models.activity import ActivityItem, EmissionEstimate

logger = get_logger(__name__)


class EmissionFactorRegistry:
    """Authoritative kgCO2e-per-unit factors and the estimation math."""

    # factor_key -> (kgCO2e per unit, unit, human label, category)
    FACTORS = {
        "transport.car_petrol_km": (0.18, "km", "Petrol car travel", ActivityCategory.TRANSPORT),
        "transport.car_diesel_km": (0.16, "km", "Diesel car travel", ActivityCategory.TRANSPORT),
        "transport.bike_petrol_km": (0.06, "km", "Two-wheeler travel", ActivityCategory.TRANSPORT),
        "transport.auto_rickshaw_km": (0.08, "km", "Auto-rickshaw travel", ActivityCategory.TRANSPORT),
        "transport.bus_km": (0.054, "km", "Bus travel", ActivityCategory.TRANSPORT),
        "transport.metro_km": (0.015, "km", "Metro travel", ActivityCategory.TRANSPORT),
        "transport.train_km": (0.014, "km", "Rail travel", ActivityCategory.TRANSPORT),
        "transport.flight_domestic_km": (0.246, "km", "Domestic flight", ActivityCategory.TRANSPORT),
        "transport.cycle_km": (0.0, "km", "Cycling", ActivityCategory.TRANSPORT),
        "transport.walk_km": (0.0, "km", "Walking", ActivityCategory.TRANSPORT),
        "energy.grid_kwh_in": (0.71, "kWh", "Grid electricity (India avg)", ActivityCategory.ENERGY),
        "energy.ac_hour": (1.07, "hours", "Air conditioning (1.5T split)", ActivityCategory.ENERGY),
        "energy.lpg_kg": (2.98, "kg", "LPG cooking gas", ActivityCategory.ENERGY),
        "food.meal_nonveg": (2.0, "meals", "Non-vegetarian meal", ActivityCategory.FOOD),
        "food.meal_veg": (0.7, "meals", "Vegetarian meal", ActivityCategory.FOOD),
        "food.meal_vegan": (0.5, "meals", "Vegan meal", ActivityCategory.FOOD),
        "food.dairy_litre": (1.4, "litres", "Dairy milk", ActivityCategory.FOOD),
        "food.delivery_order": (0.5, "orders", "Food delivery packaging+trip", ActivityCategory.FOOD),
        "shopping.apparel_item": (8.0, "items", "New apparel item", ActivityCategory.SHOPPING),
        "shopping.electronics_small": (25.0, "items", "Small electronics purchase", ActivityCategory.SHOPPING),
        "shopping.parcel_delivery": (0.6, "parcels", "E-commerce parcel delivery", ActivityCategory.SHOPPING),
    }

    # Where Gemini cannot find an exact factor it proposes the nearest
    # one; this alias map also absorbs common interpretation variants.
    ALIASES = {
        "transport.car_km": "transport.car_petrol_km",
        "transport.cab_km": "transport.car_petrol_km",
        "transport.scooter_km": "transport.bike_petrol_km",
        "energy.electricity_kwh": "energy.grid_kwh_in",
        "food.meal_chicken": "food.meal_nonveg",
        "food.meal_mutton": "food.meal_nonveg",
    }

    def resolve_factor_key(self, factor_key: str) -> str:
        """Normalise a proposed key to a canonical registry key."""
        key = (factor_key or "").strip().lower()
        key = self.ALIASES.get(key, key)
        if key not in self.FACTORS:
            raise EstimationError(f"Unknown emission factor: {factor_key}")
        return key

    def estimate(self, item: ActivityItem) -> EmissionEstimate:
        """Deterministically cost one activity item in kgCO2e."""
        if item.quantity is None or item.quantity < 0:
            raise EstimationError("Activity quantity must be a non-negative number.")
        key = self.resolve_factor_key(item.factor_key)
        per_unit, unit, label, category = self.FACTORS[key]
        emission = round(per_unit * float(item.quantity), 3)
        return EmissionEstimate(
            factor_key=key,
            label=label,
            category=category.value,
            quantity=float(item.quantity),
            unit=unit,
            emission_kg_co2e=emission,
            confidence=item.confidence,
        )

    def estimate_batch(self, items: list) -> tuple:
        """Cost a batch of items; returns (estimates, total_kg_co2e).

        Items with unknown factors are skipped with a warning rather than
        failing the whole request — one unparseable clause should not
        discard a user's entire day of tracking.
        """
        estimates = []
        for item in items:
            try:
                estimates.append(self.estimate(item))
            except EstimationError as exc:
                logger.warning("Skipping unestimable item %s: %s", item.factor_key, exc)
        total = round(sum(e.emission_kg_co2e for e in estimates), 3)
        return estimates, total

    def factor_catalog(self) -> dict:
        """Expose the factor table for the UI quick-add chips and README."""
        return {
            key: {"per_unit_kg_co2e": v[0], "unit": v[1], "label": v[2], "category": v[3].value}
            for key, v in self.FACTORS.items()
        }

    def is_healthy(self) -> bool:
        """The registry is in-process and always available."""
        return bool(self.FACTORS)
