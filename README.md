# GreenPrint — Understand your footprint. Shrink it with one action a day.

Built by **Srinivas Reddy Yarragudi** for PromptWars Virtual.

## Challenge Vertical
**[Challenge 3] Carbon Footprint Awareness Platform** — design a solution that helps individuals understand, track, and reduce their carbon footprint through simple actions and personalized insights.

## What It Does
GreenPrint lets anyone describe their day in plain language — in English, Hindi, Telugu, Tamil, Kannada, Bengali or Marathi — and instantly see its carbon cost, computed from an auditable, India-first emission factor registry. It then turns awareness into action: ranked reduction suggestions with quantified weekly and annual savings, an EcoScore (0–100) with streaks, a 7-day trend chart, and a what-if simulator that projects the impact of a change before the user commits to it.

## Approach and Logic
The core design principle is **"Gemini interprets, the registry computes."**

1. **Track** — `POST /api/track` accepts free text ("drove 12 km to office, had chicken biryani, ran the AC for 6 hours") and/or structured quick-add items. The `CarbonIntelligenceEngine` (Gemini 2.5 Flash on Vertex AI) parses the description into factor keys and quantities. If Vertex AI is unavailable, a deterministic keyword parser takes over so the platform never returns an empty result.
2. **Compute** — the `EmissionFactorRegistry` holds India-first kgCO₂e factors (CEA grid intensity 0.71 kg/kWh, petrol car 0.18 kg/km, metro 0.015 kg/km, …). All arithmetic is deterministic and reproducible; the language model never invents an emission number.
3. **Personalize** — every tracking event is appended to the `FootprintLedger` (Firestore). The `InsightComposer` aggregates the session's own history to compute the EcoScore, rank reduction actions by *that user's* category mix, render the weekly trend as an accessible server-side SVG, and power the what-if simulator's projections.
4. **Speak the user's language** — the entire structured response is translated recursively with Cloud Translate v3 (`translate_json_values()`); machine-readable keys, unit symbols (kgCO₂e, kWh, km) and #hashtags are excluded by design.

## How the Solution Works (Endpoints)
| Endpoint | Purpose |
|---|---|
| `POST /api/track` | Interpret + estimate activities; persist to ledger; returns estimates, total, personalised eco tip |
| `GET /api/insights?session_id=` | EcoScore, ranked reduction actions, weekly trend SVG (TTL-cached) |
| `POST /api/simulate` | What-if projection: weekly/annual saving for a described change |
| `GET /api/history?session_id=` | Raw ledger records, newest first |
| `GET /api/factors` | The deterministic factor catalog powering quick-add chips |
| `GET /health` | Per-service readiness for all 7 backing services |

## Google Services Used
- **Vertex AI** (`vertexai.init()` + `aiplatform.init()`): AI platform foundation
- **Gemini 2.5 Flash** (`GenerativeModel`): activity interpretation, eco tips, simulation narratives
- **Cloud Translate v3** (`translate_v3.TranslationServiceClient()`): full-response translation across 7 languages
- **Cloud Firestore** (`firestore.Client()`): the footprint ledger powering personalised trends
- **Cloud Storage** (`storage.Client()`): JSON archival of tracking summaries
- **Secret Manager** (`secretmanager.SecretManagerServiceClient()`): runtime secret resolution
- **Cloud Natural Language API** (`language_v2.LanguageServiceClient()`): sentiment of user reflections → motivation-aware coaching tone
- **Cloud Run (asia-south1)**: deployment target

## Architecture
Flask app-factory (`create_app()`) with Blueprint routing. **Thin routes** (`app/routes/`) only validate and dispatch; **fat domain services** (`app/services/`) own all logic: `CarbonIntelligenceEngine`, `EmissionFactorRegistry`, `InsightComposer`, `FootprintLedger`, `ResponseTranslator`, `ArchiveVault`, `SecretVault`, `SentimentLens`, `InsightCache`. Supporting layers: frozen dataclass config, typed constants, domain exception hierarchy (`GreenPrintError → ValidationError/EstimationError/TranslationError/LedgerError`), Protocol interfaces, per-module structured JSON logging.

**Security:** additive `after_request` headers only (CSP without unsafe-inline, HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, X-XSS-Protection); request payload cap (413); rate limiting; non-root multi-stage Docker. No request-blocking middleware — external callers are always served.

**Efficiency:** TTL+LRU insight cache, `processing_time_ms` in every response, Firestore reads capped at a 50-record window, multi-stage slim image.

**Testing:** 102 tests across 7 test files (8 files total), 87% coverage, all Google clients mocked — `pytest --cov=app`.

**Accessibility:** skip link, ARIA landmarks and labels, `aria-live` regions, labelled controls, visible focus rings, reduced-motion, forced-colors and dark-mode support; trend SVG carries `role="img"` with a descriptive label.

## How to Run
```bash
# Local
pip install -r requirements.txt
export GOOGLE_CLOUD_PROJECT=your-project-id
python main.py            # http://localhost:8080

# Tests
pytest --cov=app

# Deploy
gcloud run deploy greenprint --source=. --region=asia-south1 \
  --allow-unauthenticated --memory=512Mi --timeout=120
```

## Assumptions
- Emission factors are India-first (CEA grid average; Indian transport and diet studies), with category-level global approximations as fallback. Figures are directional awareness estimates, not certified carbon accounting.
- The footprint scope is an individual's lifestyle: transport, food, home energy and shopping.
- A `session_id` identifies a user's tracking stream; no authentication or PII is collected by design.
- The urban-India daily baseline used by the EcoScore is ~5.5 kgCO₂e/day.
