"""CarbonIntelligenceEngine — GreenPrint's activity interpreter.

Role in the product: convert a user's plain-language description of
their day ("drove 12 km to office, ordered biryani, ran the AC for 6
hours") into structured `ActivityItem`s keyed to the deterministic
EmissionFactorRegistry. The engine also drafts the personalised eco tip
and the what-if simulation narrative.

Resilience: if Vertex AI is unavailable or quota-exhausted during
evaluation, a deterministic keyword parser produces a best-effort
interpretation so the platform never returns an empty result.
"""
import json
import re

import vertexai
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel

from app.exceptions import EstimationError
from app.logging_config import get_logger
from app.models.activity import ActivityItem

logger = get_logger(__name__)

_INTERPRET_PROMPT = """You are the activity interpreter for GreenPrint, a carbon
footprint awareness platform. Convert the user's description of their day into a
JSON array of activities. Each element must be:
{{"factor_key": <one of the keys below>, "quantity": <number>, "note": <short phrase>,
"confidence": <0.0-1.0>}}

Valid factor keys and units:
{catalog}

Rules:
- Quantities must be numbers in the factor's unit (km, kWh, hours, meals, items).
- If the user gives no quantity, infer a typical one and set confidence below 0.8.
- If an activity has no close factor, pick the nearest and lower confidence.
- Respond with ONLY the JSON array. No markdown, no commentary.

User description: {text}
"""

# Deterministic fallback vocabulary: (regex, factor_key, default_quantity).
# Quantities are captured when the user states "<number> km/hours/meals".
_FALLBACK_RULES = (
    (r"(metro)", "transport.metro_km", 10.0),
    (r"(bus)", "transport.bus_km", 10.0),
    (r"(train|rail)", "transport.train_km", 20.0),
    (r"(flight|flew)", "transport.flight_domestic_km", 500.0),
    (r"(bike|scooter|two.?wheeler)", "transport.bike_petrol_km", 8.0),
    (r"(auto|rickshaw)", "transport.auto_rickshaw_km", 6.0),
    (r"(car|drove|cab|taxi)", "transport.car_petrol_km", 10.0),
    (r"(cycle|cycling|bicycle)", "transport.cycle_km", 5.0),
    (r"(a\.?c\.?|air.?condition)", "energy.ac_hour", 4.0),
    (r"(electricity|kwh)", "energy.grid_kwh_in", 5.0),
    (r"(lpg|cooking gas)", "energy.lpg_kg", 0.5),
    (r"(chicken|mutton|fish|biryani|non.?veg)", "food.meal_nonveg", 1.0),
    (r"(vegan)", "food.meal_vegan", 1.0),
    (r"(veg|salad|dal|sabzi)", "food.meal_veg", 1.0),
    (r"(delivery|swiggy|zomato|ordered)", "food.delivery_order", 1.0),
    (r"(clothes|shirt|apparel|dress)", "shopping.apparel_item", 1.0),
    (r"(parcel|amazon|flipkart)", "shopping.parcel_delivery", 1.0),
)

_QUANTITY_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(km|kilometer|kilometre|kwh|hour|hrs?|meal|item)", re.IGNORECASE)


class CarbonIntelligenceEngine:
    """Gemini-backed interpreter with a deterministic safety net."""

    def __init__(self, config, registry):
        self._config = config
        self._registry = registry
        self._model = None
        self._initialized = False

    def _ensure_model(self) -> GenerativeModel:
        """Initialise Vertex AI lazily — once per process, never per request."""
        if not self._initialized:
            vertexai.init(project=self._config.project_id, location=self._config.location)
            aiplatform.init(project=self._config.project_id, location=self._config.location)
            self._model = GenerativeModel(self._config.gemini_model_name)
            self._initialized = True
        return self._model

    # ------------------------------------------------------------------
    # Activity interpretation
    # ------------------------------------------------------------------
    def interpret_activity(self, text: str) -> list:
        """Interpret free text into ActivityItems (Gemini, then fallback)."""
        if not text or not text.strip():
            raise EstimationError("No activity description provided.")
        try:
            return self._interpret_with_gemini(text)
        except Exception as exc:  # Vertex outage/quota must never empty a response.
            logger.warning("Gemini interpretation unavailable (%s); using heuristic parser.", exc)
            return self._heuristic_parse(text)

    def _interpret_with_gemini(self, text: str) -> list:
        catalog = "\n".join(
            f"- {key} (unit: {meta['unit']}, {meta['label']})"
            for key, meta in self._registry.factor_catalog().items()
        )
        prompt = _INTERPRET_PROMPT.format(catalog=catalog, text=text.strip())
        response = self._ensure_model().generate_content(prompt)
        return self._parse_model_json(response.text)

    def _parse_model_json(self, raw: str) -> list:
        """Extract the JSON array from a model response, tolerating fences."""
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise EstimationError("Model response contained no activity array.")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise EstimationError("Model response was not valid JSON.") from exc
        items = []
        for entry in parsed:
            if not isinstance(entry, dict) or "factor_key" not in entry:
                continue
            items.append(
                ActivityItem(
                    factor_key=str(entry.get("factor_key", "")),
                    quantity=float(entry.get("quantity", 0) or 0),
                    note=str(entry.get("note", ""))[:120],
                    confidence=float(entry.get("confidence", 0.9) or 0.9),
                )
            )
        if not items:
            raise EstimationError("Model produced no usable activities.")
        return items

    def _heuristic_parse(self, text: str) -> list:
        """Deterministic keyword interpretation used when Gemini is down."""
        lowered = text.lower()
        quantity_match = _QUANTITY_PATTERN.search(lowered)
        stated_quantity = float(quantity_match.group(1)) if quantity_match else None
        items, used_stated = [], False
        for pattern, factor_key, default_qty in _FALLBACK_RULES:
            if re.search(pattern, lowered):
                quantity = default_qty
                # The first matched activity claims any stated quantity.
                if stated_quantity is not None and not used_stated:
                    quantity, used_stated = stated_quantity, True
                items.append(
                    ActivityItem(factor_key=factor_key, quantity=quantity, note="heuristic match", confidence=0.5)
                )
        if not items:
            raise EstimationError("Could not recognise any trackable activity in the description.")
        return items

    # ------------------------------------------------------------------
    # Narrative generation (tips + simulations)
    # ------------------------------------------------------------------
    def draft_eco_tip(self, estimates: list, total_kg: float) -> str:
        """One personalised, actionable tip for this tracking event."""
        try:
            top = max(estimates, key=lambda e: e.emission_kg_co2e)
            prompt = (
                "In under 35 words, give one upbeat, specific tip to reduce the "
                f"largest item of this footprint: {top.label}, "
                f"{top.emission_kg_co2e} kgCO2e of a {total_kg} kgCO2e day. "
                "No preamble, plain text."
            )
            return self._ensure_model().generate_content(prompt).text.strip()
        except Exception:
            return self._fallback_tip(estimates)

    def _fallback_tip(self, estimates: list) -> str:
        if not estimates:
            return "Log one activity a day — awareness is the first reduction."
        top = max(estimates, key=lambda e: e.emission_kg_co2e)
        tips = {
            "transport": "Swap one short car trip this week for metro, bus or cycling.",
            "energy": "Raise the AC set-point by 1°C — it cuts cooling energy by about 6%.",
            "food": "Try one extra vegetarian meal this week — about 1.3 kgCO2e saved per swap.",
            "shopping": "Batch online orders into one delivery to cut parcel trips.",
        }
        return tips.get(top.category, "Small daily swaps compound into real reductions.")

    def draft_simulation_narrative(self, scenario: str, saving_kg: float) -> str:
        """Short narrative for the what-if simulator."""
        try:
            prompt = (
                f"In under 40 words, encourage a user whose scenario '{scenario}' "
                f"would save {saving_kg} kgCO2e per week. Plain text, no preamble."
            )
            return self._ensure_model().generate_content(prompt).text.strip()
        except Exception:
            return (
                f"This change saves about {saving_kg} kgCO2e every week — "
                f"roughly {round(saving_kg * 52, 1)} kg a year. Worth starting today."
            )

    def is_healthy(self) -> bool:
        """Healthy if Vertex AI is initialisable; heuristics cover outages."""
        try:
            self._ensure_model()
            return True
        except Exception:
            return False
