"""API routes for GreenPrint — thin by design.

Routes validate, dispatch to domain services, attach processing-time
metadata, translate the full response and return. All carbon logic lives
in app/services; nothing here computes an emission.
"""
from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

from flask import Blueprint, current_app, jsonify, request

from app.constants import DEFAULT_LANGUAGE
from app.exceptions import ValidationError
from app.logging_config import get_logger
from app.models.activity import ActivityItem, ActivityRecord

if TYPE_CHECKING:
    from app import ServiceContainer
    from app.models.activity import EmissionEstimate

logger = get_logger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api")


def _services() -> ServiceContainer:
    return current_app.extensions["greenprint_services"]


def _json_body() -> dict[str, Any]:
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object.")
    return body


def _finalize(payload: dict[str, Any], language: str, started_at: float) -> Any:
    """Attach timing metadata, translate the full response, and respond."""
    payload["processing_time_ms"] = int((time.perf_counter() - started_at) * 1000)
    payload["language"] = language
    translated = _services().translator.translate_response(payload, language)
    return jsonify(translated)


def _extract_structured_items(body: dict[str, Any]) -> list[ActivityItem]:
    """Extract ActivityItems from JSON body activities list."""
    items: list[ActivityItem] = []
    for raw in body.get("activities", []):
        if isinstance(raw, dict) and raw.get("factor_key") is not None:
            items.append(
                ActivityItem(
                    factor_key=str(raw["factor_key"]),
                    quantity=float(raw.get("quantity", 0) or 0),
                    note=str(raw.get("note", ""))[:120],
                )
            )
    return items


def _compose_track_payload(
    session_id: str,
    estimates: list[EmissionEstimate],
    total: float,
    eco_tip: str,
    motivation_tone: str,
) -> dict[str, Any]:
    """Assemble the tracking response payload dictionary."""
    return {
        "status": "ok",
        "session_id": session_id,
        "estimates": [estimate.to_dict() for estimate in estimates],
        "total_kg_co2e": total,
        "eco_tip": eco_tip,
        "motivation_tone": motivation_tone,
    }


@api_bp.route("/track", methods=["POST"])
def track_activity() -> Any:
    """Track activities from free text and/or structured quick-add items."""
    started_at = time.perf_counter()
    services = _services()
    body = _json_body()
    language = str(body.get("language", DEFAULT_LANGUAGE)).lower()
    session_id = str(body.get("session_id") or uuid.uuid4())
    text = str(body.get("text", "")).strip()

    items = _extract_structured_items(body)
    if text:
        items.extend(services.engine.interpret_activity(text))
    if not items:
        raise ValidationError("Provide 'text' or a non-empty 'activities' list.")

    estimates, total = services.registry.estimate_batch(items)
    if not estimates:
        raise ValidationError("No recognisable activities could be estimated.")

    record = ActivityRecord(
        session_id=session_id,
        estimates=estimates,
        total_kg_co2e=total,
        source_text=text[:500],
    )
    services.ledger.append_record(record)
    services.cache.invalidate_prefix(("insights", session_id))
    services.vault.archive_summary(session_id, record.to_dict())
    motivation = services.sentiment.gauge_motivation(text)

    eco_tip = services.engine.draft_eco_tip(estimates, total)
    payload = _compose_track_payload(
        session_id, estimates, total, eco_tip, motivation["tone"]
    )
    return _finalize(payload, language, started_at)


@api_bp.route("/insights", methods=["GET"])
def session_insights() -> Any:
    """Personalised insights: EcoScore, ranked actions, weekly trend SVG."""
    started_at = time.perf_counter()
    services = _services()
    session_id = request.args.get("session_id", "").strip()
    language = request.args.get("language", DEFAULT_LANGUAGE).lower()
    if not session_id:
        raise ValidationError("Query parameter 'session_id' is required.")

    cached = services.cache.get(("insights", session_id, language))
    if cached is not None:
        return jsonify(cached)

    history = services.ledger.session_history(session_id)
    summary = services.composer.summarize(history)
    payload = {
        "status": "ok",
        "session_id": session_id,
        "summary": summary.to_dict(),
        "eco_score": services.composer.eco_score(history),
        "top_actions": [a.to_dict() for a in services.composer.rank_reduction_actions(summary)],
        "weekly_trend_svg": services.composer.weekly_trend_svg(history),
    }
    response = _finalize(payload, language, started_at)
    services.cache.set(("insights", session_id, language), response.get_json())
    return response


@api_bp.route("/simulate", methods=["POST"])
def simulate_scenario() -> Any:
    """What-if simulator: project savings for a described behaviour change."""
    started_at = time.perf_counter()
    services = _services()
    body = _json_body()
    scenario = str(body.get("scenario", "")).strip()
    language = str(body.get("language", DEFAULT_LANGUAGE)).lower()
    session_id = str(body.get("session_id", "")).strip()
    if not scenario:
        raise ValidationError("A 'scenario' description is required.")

    history = services.ledger.session_history(session_id) if session_id else []
    summary = services.composer.summarize(history)
    projection = services.composer.simulate(summary, scenario)
    projection["narrative"] = services.engine.draft_simulation_narrative(
        scenario, float(projection["weekly_saving_kg"])
    )
    payload = {"status": "ok", **projection}
    return _finalize(payload, language, started_at)


@api_bp.route("/history", methods=["GET"])
def session_history() -> Any:
    """Raw ledger records for a session (newest first)."""
    started_at = time.perf_counter()
    services = _services()
    session_id = request.args.get("session_id", "").strip()
    language = request.args.get("language", DEFAULT_LANGUAGE).lower()
    if not session_id:
        raise ValidationError("Query parameter 'session_id' is required.")
    records = services.ledger.session_history(session_id)
    payload = {"status": "ok", "session_id": session_id, "records": records, "count": len(records)}
    return _finalize(payload, language, started_at)


@api_bp.route("/factors", methods=["GET"])
def factor_catalog() -> Any:
    """Expose the deterministic factor table powering quick-add chips."""
    started_at = time.perf_counter()
    payload = {"status": "ok", "factors": _services().registry.factor_catalog()}
    return _finalize(payload, DEFAULT_LANGUAGE, started_at)
