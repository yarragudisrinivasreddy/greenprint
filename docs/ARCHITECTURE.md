# GreenPrint Architecture

## System Overview

GreenPrint is structured around clean architecture principles. All dependencies point inward toward the core business domain. Backing services (Google Cloud Vertex AI, Translate, Firestore, Storage) degrade gracefully to local in-memory fallbacks when unauthenticated or offline.

## Layer Table

| Layer | Responsibility | Components | Dependencies |
|---|---|---|---|
| **Presentation / Routes** | Web interface and HTTP endpoints. Thin validation and routing. | `app.js`, `api.py`, `health.py` | `app/services/`, `app/repository/` |
| **Domain Services** | Personalization, translation wrapper, sentiment coaching. | `insight_composer.py`, `translator.py`, `sentiment_lens.py` | `app/models/`, `app/repository/` |
| **Google Cloud Gateways** | Verification, LLM prompting, and Vertex/GCS integration. | `vertex_gateway.py`, `activity_interpreter.py`, `narrative_composer.py` | `app/config.py` |
| **Persistence / Repositories** | Decoupled storage for footprint summaries and history. | `base.py`, `firestore_repo.py`, `memory_repo.py` | `app/models/` |
| **Core Models** | Immutable types representing tracking, estimates, and health. | `activity.py`, `insight.py`, `health.py` | None (pure models) |

## System Dependency Flow

```
+--------------------------------------------------------------+
|                    Presentation / routes                     |
|                   (api.py, health.py, app.js)                 |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
|                       Domain Services                        |
|       (insight_composer.py, translator.py, sentiment_lens.py) |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
|                     Google Cloud Gateways                    |
| (activity_interpreter.py, narrative_composer.py, gateway.py)  |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
|                    Persistence / Repository                  |
|    (base.py, selector/footprint_ledger.py, firestore_repo)   |
+--------------------------------------------------------------+
```

## Architectural Design Rules

1. **Dependencies Point Inward**: Outer layers depend on inner core protocols and models. Inner layers (like the deterministic `EmissionFactorRegistry` or `LedgerRepository` protocol) never import routes or external frameworks.
2. **Graceful Degradation**:
   - If Vertex AI / Gemini fails, the activity interpreter automatically falls back to regex-based keyword parsing (`_heuristic_parse`).
   - If Firestore is offline or fails authentication, the coordinates selector ledger (`FootprintLedger`) reads/writes to a bounded `InMemoryLedger` instead.
   - If Cloud Translate fails, translatable fields pass through in English without failing the request.
3. **No Secrets committed**: All GCP API keys or configurations are read from `Config` (loaded via Environment Variables or runtime `SecretVault` resolution). No sensitive credentials or hardcoded keys reside in source code.
