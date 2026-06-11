"""ActivityInterpreter — parses plain text descriptions into structured activities.

Why: Segregates plain language parsing from narrative generation to improve maintainability,
adhere to single responsibility principles, and simplify unit testing.
"""
# pylint: disable=duplicate-code
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import google.api_core.exceptions
import google.auth.exceptions

from app.exceptions import EstimationError
from app.logging_config import get_logger
from app.models.activity import ActivityItem

if TYPE_CHECKING:
    from app.services.emission_registry import EmissionFactorRegistry
    from app.services.vertex_gateway import VertexGateway

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

_QUANTITY_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(km|kilometer|kilometre|kwh|hour|hrs?|meal|item)",
    re.IGNORECASE,
)

UPSTREAM_FAILURES = (
    google.api_core.exceptions.GoogleAPIError,
    google.auth.exceptions.GoogleAuthError,
    OSError,
    ValueError,
    json.JSONDecodeError,
)

INTERPRET_FAILURES = UPSTREAM_FAILURES + (EstimationError,)


# pylint: disable=too-few-public-methods
class ActivityInterpreter:
    """Gemini-backed interpreter with a deterministic safety net."""

    def __init__(self, gateway: VertexGateway, registry: EmissionFactorRegistry) -> None:
        self._gateway = gateway
        self._registry = registry

    def interpret_activity(self, text: str) -> list[ActivityItem]:
        """Interpret free text into ActivityItems (Gemini, then fallback)."""
        if not text or not text.strip():
            raise EstimationError("No activity description provided.")
        try:
            return self._interpret_with_gemini(text)
        except INTERPRET_FAILURES as exc:
            logger.warning("Gemini interpretation unavailable (%s); using heuristic.", exc)
            return self._heuristic_parse(text)

    def _interpret_with_gemini(self, text: str) -> list[ActivityItem]:
        catalog = "\n".join(
            f"- {key} (unit: {meta['unit']}, {meta['label']})"
            for key, meta in self._registry.factor_catalog().items()
        )
        prompt = _INTERPRET_PROMPT.format(catalog=catalog, text=text.strip())
        response = self._gateway.get_model().generate_content(prompt)
        return self._parse_model_json(response.text)

    def _strip_fences(self, raw: str) -> str:
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise EstimationError("Model response contained no activity array.")
        return match.group(0)

    def _coerce_items(self, parsed: list[Any]) -> list[ActivityItem]:
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
        return items

    def _parse_model_json(self, raw: str) -> list[ActivityItem]:
        """Extract the JSON array from a model response, tolerating fences."""
        json_str = self._strip_fences(raw)
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise EstimationError("Model response was not valid JSON.") from exc
        if not isinstance(parsed, list):
            raise EstimationError("Model response was not a JSON array.")
        items = self._coerce_items(parsed)
        if not items:
            raise EstimationError("Model produced no usable activities.")
        return items

    def _heuristic_parse(self, text: str) -> list[ActivityItem]:
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
                    ActivityItem(
                        factor_key=factor_key,
                        quantity=quantity,
                        note="heuristic match",
                        confidence=0.5,
                    )
                )
        if not items:
            raise EstimationError("Could not recognise any trackable activity.")
        return items
