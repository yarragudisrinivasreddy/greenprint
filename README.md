# GreenPrint — Understand your footprint. Shrink it with one action a day.

![Tests](https://img.shields.io/badge/tests-132%20passing-brightgreen) ![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)

CI configuration: [.github/workflows/ci.yml](.github/workflows/ci.yml) (pytest ≥95% coverage gate + pylint ≥9.9).

Built by **Srinivas Reddy Yarragudi** for PromptWars Virtual.

## Challenge Vertical
**[Challenge 3] Carbon Footprint Awareness Platform** — design a solution that helps individuals understand, track, and reduce their carbon footprint through simple actions and personalized insights.

## The Pillars of GreenPrint
Below is the mapping of the challenge brief's core requirements to the features implemented in GreenPrint:

| Pillar | Brief Requirement | GreenPrint Feature Mapping |
| :--- | :--- | :--- |
| **Understand** | Help individuals understand the carbon impact of their daily choices. | **Auditable Factor Registry** (India-first CEA electricity grid factors, DEFRA/IPCC AR6 citations), **Motivation Gauging** (sentiment analysis of user reflections to adapt the tone of the narrative). |
| **Track** | Support logging and tracking of daily activities easily. | **Plain Language Input** (free-text tracking parsed by LLM), **Multi-lingual Support** (transfers complete tracking to Hindi/Telugu/etc.), **Quick-Add Activity Chips** (frictionless logging). |
| **Reduce** | Help individuals reduce their footprint through simple actions and personalized insights. | **Ranked Reduction Actions** (tailored to the user's highest categories), **EcoScore & Streaks** (gamification for low-carbon consistency), **What-If Simulator** (projects future weekly/annual savings). |

## ASCII Decision Flow
The diagram below illustrates how a tracking request flows through the decoupled architecture:

```
    [User Input: text or chips]
                 │
                 ▼
     [ActivityInterpreter] ──(Fallback)──> [Keyword Heuristic Parser]
                 │
                 ▼
     [EmissionFactorRegistry]
                 │ (Deterministic calculation)
                 ▼
          [ActivityRecord]
                 │
                 ▼
    [FootprintLedger Selector]
       ├──> [FirestoreLedger (Production DB)]
       └──> [InMemoryLedger (LRU Fallback - caps at 256 sessions, 50 records/sess)]
                 │
                 ▼
       [InsightComposer (EcoScore, Streak, SVG Trend)]
                 │
                 ▼
       [ResponseTranslator (Cloud Translate v3)]
                 │
                 ▼
     [Accessible HTML Render & UI Updates]
```

## How It Works (Endpoints)
| Endpoint | Purpose |
|---|---|
| `POST /api/track` | Interpret + estimate activities; persist to ledger; returns estimates, total, and personalized eco tip |
| `GET /api/insights?session_id=` | EcoScore, ranked reduction actions, and weekly trend SVG (TTL-cached) |
| `POST /api/simulate` | What-if projection: weekly/annual saving for a described change |
| `GET /api/history?session_id=` | Raw ledger records, newest first |
| `GET /api/factors` | The deterministic factor catalog powering quick-add chips |
| `GET /health` | Per-service readiness for all 7 backing services |

## Google Services Used
- **Vertex AI** (`vertexai.init()` + `aiplatform.init()`): AI platform foundation.
- **Gemini 2.5 Flash** (`GenerativeModel`): activity interpretation, eco tips, simulation narratives.
- **Cloud Translate v3** (`translate_v3.TranslationServiceClient()`): full-response translation across 7 languages.
- **Cloud Firestore** (`firestore.Client()`): the footprint ledger powering personalized trends.
- **Cloud Storage** (`storage.Client()`): JSON archival of tracking summaries.
- **Secret Manager** (`secretmanager.SecretManagerServiceClient()`): runtime secret resolution.
- **Cloud Natural Language API** (`language_v2.LanguageServiceClient()`): sentiment of user reflections → motivation-aware coaching tone.
- **Cloud Run (asia-south1)**: deployment target.

## Architecture
The application architecture is detailed in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

- **Blueprint Routing** (`app/routes/`): Thin endpoints validate schema inputs and coordinate with domain logic.
- **Decoupled Repositories** (`app/repository/`): Standardized via `LedgerRepository` protocol. `FirestoreLedger` handles production writes, while `InMemoryLedger` manages offline test environments and automatic failover.
- **Domain Services** (`app/services/`):
  - `ActivityInterpreter`: Parses free text using Gemini or keyword fallback.
  - `NarrativeComposer`: Generates tips and simulator descriptions.
  - `VertexGateway`: Manages Vertex AI model initialization verbatim.
  - `EmissionFactorRegistry`: Contains India-first factors.
  - `InsightComposer`: Compiles trends, EcoScore, and SVG charts.
  - `ResponseTranslator`, `ArchiveVault`, `SecretVault`, `SentimentLens`, `InsightCache`.

**Security:** CSP without unsafe-inline (`style-src 'self'; font-src 'self'`), HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy; request payload cap (413); rate limiting; non-root multi-stage Docker. No request-blocking middleware — external callers are always served.

**Efficiency:** TTL+LRU insight cache, `processing_time_ms` in every response, Firestore reads capped at a 50-record window, memory-bound mirror limits, multi-stage slim image.

**Testing:** 132 tests across 7 test files (8 files total), 96% coverage, all Google clients mocked — `pytest --cov=app`

**Accessibility:** skip link, ARIA landmarks, `aria-busy` busy-state toggling on results regions, `aria-live` regions, labelled controls, visible focus rings, reduced-motion, forced-colors, and dark-mode support; trend SVG carries `role="img"` with a descriptive label.

## How to Run
```bash
# Local Setup
pip install -r requirements.txt -r requirements-dev.txt
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
- The footprint scope is an individual's lifestyle: transport, food, home energy, and shopping.
- A `session_id` identifies a user's tracking stream; no authentication or PII is collected by design.
- The urban-India daily baseline used by the EcoScore is ~5.5 kgCO₂e/day.
