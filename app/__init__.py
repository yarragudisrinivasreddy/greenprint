# pylint: disable=import-outside-toplevel,too-many-instance-attributes
"""GreenPrint application factory.

`create_app()` wires configuration, logging, security headers, rate
limiting and the domain service container, then registers Blueprints.
Tests construct apps with injected fakes via the same factory.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.config import load_config
from app.exceptions import GreenPrintError
from app.logging_config import configure_logging, get_logger
from app.security import register_security

if TYPE_CHECKING:
    from app.config import Config
    from app.services.archive_vault import ArchiveVault
    from app.services.activity_interpreter import ActivityInterpreter
    from app.services.emission_registry import EmissionFactorRegistry
    from app.repository.base import LedgerRepository
    from app.services.insight_cache import InsightCache
    from app.services.insight_composer import InsightComposer
    from app.services.secret_vault import SecretVault
    from app.services.sentiment_lens import SentimentLens
    from app.services.translator import ResponseTranslator
    from app.services.vertex_gateway import VertexGateway
    from app.services.narrative_composer import NarrativeComposer

logger = get_logger(__name__)


@dataclass
class ServiceContainer:
    """All domain services GreenPrint routes depend on."""

    registry: EmissionFactorRegistry
    interpreter: ActivityInterpreter
    composer: InsightComposer
    narrator: NarrativeComposer
    ledger: LedgerRepository
    translator: ResponseTranslator
    vault: ArchiveVault
    secrets: SecretVault
    sentiment: SentimentLens
    cache: InsightCache
    gateway: VertexGateway


def build_services(config: Config) -> ServiceContainer:
    """Construct the production service graph (lazy Google clients)."""
    from app.services.archive_vault import ArchiveVault
    from app.services.activity_interpreter import ActivityInterpreter
    from app.services.emission_registry import EmissionFactorRegistry
    from app.repository.firestore_repo import FirestoreLedger
    from app.repository.memory_repo import InMemoryLedger
    from app.services.footprint_ledger import FootprintLedger
    from app.services.insight_cache import InsightCache
    from app.services.insight_composer import InsightComposer
    from app.services.secret_vault import SecretVault
    from app.services.sentiment_lens import SentimentLens
    from app.services.translator import ResponseTranslator
    from app.services.vertex_gateway import VertexGateway
    from app.services.narrative_composer import NarrativeComposer

    registry = EmissionFactorRegistry()
    gateway = VertexGateway(config)

    firestore_repo = FirestoreLedger(config)
    memory_repo = InMemoryLedger()
    ledger = FootprintLedger(firestore_repo, memory_repo, config)

    return ServiceContainer(
        registry=registry,
        interpreter=ActivityInterpreter(gateway, registry),
        composer=InsightComposer(),
        narrator=NarrativeComposer(gateway),
        ledger=ledger,
        translator=ResponseTranslator(config),
        vault=ArchiveVault(config),
        secrets=SecretVault(config),
        sentiment=SentimentLens(),
        cache=InsightCache(config.insight_cache_ttl_seconds, config.insight_cache_max_entries),
        gateway=gateway,
    )


def create_app(services: ServiceContainer | None = None) -> Flask:
    """Build the Flask application; `services` is injectable for tests."""
    configure_logging()
    config = load_config()

    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config["MAX_CONTENT_LENGTH"] = config.max_request_bytes
    app.extensions["greenprint_services"] = services or build_services(config)

    register_security(app)

    # Using memory:// storage — Redis recommended for multi-worker
    # production so all gunicorn workers share one limit state.
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["120 per minute"],
        storage_uri="memory://",
    )
    app.extensions["greenprint_limiter"] = limiter

    from app.routes.api import api_bp
    from app.routes.health import health_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(health_bp)

    @app.errorhandler(GreenPrintError)
    def handle_domain_error(error: GreenPrintError) -> Any:
        logger.warning("Domain error: %s", error)
        return jsonify({"status": "error", "message": error.public_message}), error.status_code

    @app.errorhandler(404)
    def handle_not_found(_: Any) -> Any:
        return jsonify({"status": "error", "message": "Resource not found."}), 404

    @app.errorhandler(413)
    def handle_too_large(_: Any) -> Any:
        return jsonify({"status": "error", "message": "Request payload too large."}), 413

    logger.info("GreenPrint application initialised.")
    return app
