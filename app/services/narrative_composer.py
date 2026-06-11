"""NarrativeComposer — drafts carbon footprint reduction tips and what-if scenarios.

Why: Isolates text/content generation logic from interpretation, facilitating
localized prompts, and structured translation tests.
"""
# pylint: disable=duplicate-code
from __future__ import annotations
from typing import TYPE_CHECKING

import google.api_core.exceptions
import google.auth.exceptions

from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.models.activity import EmissionEstimate
    from app.services.vertex_gateway import VertexGateway

logger = get_logger(__name__)

UPSTREAM_FAILURES = (
    google.api_core.exceptions.GoogleAPIError,
    google.auth.exceptions.GoogleAuthError,
    OSError,
    ValueError,
)


class NarrativeComposer:
    """Generates user-facing feedback narratives from emissions estimates."""

    def __init__(self, gateway: VertexGateway) -> None:
        self._gateway = gateway

    def draft_eco_tip(self, estimates: list[EmissionEstimate], total_kg: float) -> str:
        """One personalised, actionable tip for this tracking event."""
        try:
            top = max(estimates, key=lambda e: e.emission_kg_co2e)
            prompt = (
                "In under 35 words, give one upbeat, specific tip to reduce the "
                f"largest item of this footprint: {top.label}, "
                f"{top.emission_kg_co2e} kgCO2e of a {total_kg} kgCO2e day. "
                "No preamble, plain text."
            )
            return self._gateway.get_model().generate_content(prompt).text.strip()
        except UPSTREAM_FAILURES:
            return self._fallback_tip(estimates)

    def _fallback_tip(self, estimates: list[EmissionEstimate]) -> str:
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
            return self._gateway.get_model().generate_content(prompt).text.strip()
        except UPSTREAM_FAILURES:
            return (
                f"This change saves about {saving_kg} kgCO2e every week — "
                f"roughly {round(saving_kg * 52, 1)} kg a year. Worth starting today."
            )
