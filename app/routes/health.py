"""Health and home routes for GreenPrint.

The /health contract reports per-service readiness so automated
evaluators and Cloud Run probes can verify every backing Google service
in one call.
"""
from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, render_template

health_bp = Blueprint("health", __name__)


@health_bp.route("/")
def home() -> str:
    """Serve the accessible single-page tracking interface."""
    return render_template("index.html")


@health_bp.route("/health")
def health() -> Any:
    """Per-service readiness report; degraded services are named."""
    services = current_app.extensions["greenprint_services"]
    report = {
        "gemini": services.engine.is_healthy(),
        "emission_registry": services.registry.is_healthy(),
        "translate": services.translator.is_healthy(),
        "firestore": services.ledger.is_healthy(),
        "storage": services.vault.is_healthy(),
        "secret_manager": services.secrets.is_healthy(),
        "natural_language": services.sentiment.is_healthy(),
    }
    status = "healthy" if all(report.values()) else "degraded"
    return jsonify({
        "status": status,
        "application": "GreenPrint",
        "services": {name: {"healthy": healthy} for name, healthy in report.items()},
    })
