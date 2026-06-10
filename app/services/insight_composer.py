"""InsightComposer — where GreenPrint turns numbers into behaviour change.

This module owns the product's "reduce" promise: ranked reduction
actions with quantified savings, an EcoScore that rewards low-carbon
days and streaks, a server-rendered SVG weekly trend (deterministic — no
image-generation quota risk), and the what-if simulator's arithmetic.
"""
from datetime import datetime, timezone

from app.constants import ECO_SCORE_MAX, ActivityCategory
from app.logging_config import get_logger
from app.models.insight import FootprintSummary, ReductionAction

logger = get_logger(__name__)

# Awareness baseline: an average urban Indian individual's daily
# footprint (~5.5 kgCO2e/day) — the yardstick EcoScore measures against.
DAILY_BASELINE_KG = 5.5

# Swap library: (category, action template, saving per relevant kg tracked).
_SWAP_LIBRARY = {
    ActivityCategory.TRANSPORT.value: [
        ("Shift 2 car commutes a week to metro", 0.55),
        ("Cycle or walk trips under 3 km", 0.30),
    ],
    ActivityCategory.ENERGY.value: [
        ("Raise AC set-point by 1°C", 0.18),
        ("Switch remaining bulbs to LED", 0.10),
    ],
    ActivityCategory.FOOD.value: [
        ("Swap 2 non-veg meals a week for veg", 0.45),
        ("Batch food-delivery orders", 0.15),
    ],
    ActivityCategory.SHOPPING.value: [
        ("Choose consolidated parcel delivery", 0.20),
        ("Extend apparel life — repair before replace", 0.35),
    ],
}


class InsightComposer:
    """Computes summaries, EcoScore, reduction rankings and trend SVGs."""

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    def summarize(self, history: list) -> FootprintSummary:
        """Aggregate a session's ledger records into category totals."""
        category_totals = {}
        total = 0.0
        for record in history:
            for estimate in record.get("estimates", []):
                category = estimate.get("category", "other")
                emission = float(estimate.get("emission_kg_co2e", 0.0))
                category_totals[category] = round(category_totals.get(category, 0.0) + emission, 3)
                total += emission
        return FootprintSummary(
            total_kg_co2e=round(total, 3),
            record_count=len(history),
            category_totals=category_totals,
        )

    # ------------------------------------------------------------------
    # EcoScore
    # ------------------------------------------------------------------
    def eco_score(self, history: list) -> dict:
        """Score 0–100: lower-than-baseline days and streaks raise it.

        Score = 60 baseline-relative + up to 25 streak bonus + up to 15
        consistency bonus. Bounded to [0, 100]; a brand-new session
        starts at 50 (neutral awareness point).
        """
        if not history:
            return {"score": 50, "streak_days": 0, "explanation": "Start tracking to grow your score."}
        daily_totals = self._daily_totals(history)
        days = sorted(daily_totals)
        below_baseline = sum(1 for day in days if daily_totals[day] <= DAILY_BASELINE_KG)
        baseline_component = 60 * (below_baseline / len(days))
        streak = self._current_streak(days, daily_totals)
        streak_component = min(streak * 5, 25)
        consistency_component = min(len(days) * 3, 15)
        score = int(round(min(baseline_component + streak_component + consistency_component, ECO_SCORE_MAX)))
        return {
            "score": max(score, 0),
            "streak_days": streak,
            "explanation": (
                f"{below_baseline} of {len(days)} tracked days were below the "
                f"{DAILY_BASELINE_KG} kgCO2e urban baseline."
            ),
        }

    def _daily_totals(self, history: list) -> dict:
        totals = {}
        for record in history:
            day = str(record.get("recorded_at", ""))[:10] or self._today()
            totals[day] = round(totals.get(day, 0.0) + float(record.get("total_kg_co2e", 0.0)), 3)
        return totals

    def _current_streak(self, sorted_days: list, daily_totals: dict) -> int:
        streak = 0
        for day in reversed(sorted_days):
            if daily_totals[day] <= DAILY_BASELINE_KG:
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    # ------------------------------------------------------------------
    # Reduction actions
    # ------------------------------------------------------------------
    def rank_reduction_actions(self, summary: FootprintSummary, limit: int = 3) -> list:
        """Rank swaps by projected saving against THIS user's mix."""
        actions = []
        weekly_factor = 7 / max(summary.record_count, 1)
        for category, category_kg in summary.category_totals.items():
            weekly_kg = category_kg * weekly_factor
            for action_text, saving_ratio in _SWAP_LIBRARY.get(category, []):
                weekly_saving = round(weekly_kg * saving_ratio, 2)
                if weekly_saving <= 0:
                    continue
                actions.append(
                    ReductionAction(
                        action=action_text,
                        category=category,
                        weekly_saving_kg=weekly_saving,
                        annual_saving_kg=round(weekly_saving * 52, 1),
                    )
                )
        actions.sort(key=lambda a: a.weekly_saving_kg, reverse=True)
        return actions[:limit]

    # ------------------------------------------------------------------
    # What-if simulation
    # ------------------------------------------------------------------
    def simulate(self, summary: FootprintSummary, scenario: str) -> dict:
        """Project weekly footprint under a described behaviour change.

        Scenario matching is keyword-based and deterministic so the
        simulator's arithmetic is reproducible; Gemini only narrates.
        """
        weekly_factor = 7 / max(summary.record_count, 1)
        current_weekly = round(summary.total_kg_co2e * weekly_factor, 2)
        lowered = (scenario or "").lower()
        matched_category, ratio = None, 0.0
        keyword_map = (
            (("metro", "bus", "cycle", "walk", "carpool", "commute"), ActivityCategory.TRANSPORT.value, 0.5),
            (("veg", "vegan", "meat", "diet"), ActivityCategory.FOOD.value, 0.45),
            (("ac", "air condition", "electricity", "solar", "led"), ActivityCategory.ENERGY.value, 0.25),
            (("shopping", "clothes", "parcel", "order"), ActivityCategory.SHOPPING.value, 0.3),
        )
        for keywords, category, candidate_ratio in keyword_map:
            if any(word in lowered for word in keywords):
                matched_category, ratio = category, candidate_ratio
                break
        category_weekly = round(summary.category_totals.get(matched_category, 0.0) * weekly_factor, 2)
        saving = round(category_weekly * ratio, 2)
        return {
            "scenario": scenario,
            "matched_category": matched_category or "general",
            "current_weekly_kg": current_weekly,
            "projected_weekly_kg": round(max(current_weekly - saving, 0.0), 2),
            "weekly_saving_kg": saving,
            "annual_saving_kg": round(saving * 52, 1),
        }

    # ------------------------------------------------------------------
    # Weekly trend — server-rendered SVG (deterministic, quota-free)
    # ------------------------------------------------------------------
    def weekly_trend_svg(self, history: list) -> str:
        """Render the last 7 tracked days as an accessible inline SVG."""
        daily_totals = self._daily_totals(history)
        days = sorted(daily_totals)[-7:]
        values = [daily_totals[d] for d in days] or [0.0]
        width, height, pad = 560, 180, 28
        peak = max(max(values), DAILY_BASELINE_KG) or 1.0
        bar_zone = width - 2 * pad
        bar_width = bar_zone / max(len(values), 1)
        baseline_y = height - pad - (DAILY_BASELINE_KG / peak) * (height - 2 * pad)
        bars = []
        for index, value in enumerate(values):
            bar_height = (value / peak) * (height - 2 * pad)
            x = pad + index * bar_width + 4
            y = height - pad - bar_height
            color = "#2e7d32" if value <= DAILY_BASELINE_KG else "#ef6c00"
            label = days[index][5:] if index < len(days) else ""
            bars.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 8:.1f}" '
                f'height="{bar_height:.1f}" rx="4" fill="{color}">'
                f"<title>{label}: {value} kgCO2e</title></rect>"
            )
        return (
            f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="Daily carbon footprint for the last {len(values)} tracked days">'
            f'<line x1="{pad}" y1="{baseline_y:.1f}" x2="{width - pad}" y2="{baseline_y:.1f}" '
            f'stroke="#666" stroke-dasharray="6 4"/>' + "".join(bars) + "</svg>"
        )
