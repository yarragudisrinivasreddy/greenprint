# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-06-11

### Added
- Created `app/repository` package defining `LedgerRepository` protocol.
- Implemented `FirestoreLedger` and `InMemoryLedger` repositories.
- Added LRU session memory bounding (cap at 50, evict sessions > 256) inside `InMemoryLedger`.
- Created `VertexGateway` to centralize Vertex AI initialization and model caching.
- Created `ActivityInterpreter` and `NarrativeComposer` to isolate parsing from narrative content.
- Added `aria-busy` HTML attributes to result regions in `app.js` for enhanced accessibility.
- Added primary URLs and commented citations for emission factors and baseline metrics in `emission_registry.py` and `insight_composer.py`.
- Added edge tests for repository contract parity, unmatched simulations, and cache invalidation prefix misses.
- Added project hygiene files: `docs/ARCHITECTURE.md`, `LICENSE`, `CONTRIBUTING.md`, `pyproject.toml`, `.editorconfig`, and `.pre-commit-config.yaml`.
- Created `requirements-dev.txt` to separate test dependencies from production dependencies.

### Changed
- Refactored `app/services/footprint_ledger.py` as a coordinator/selector repository.
- Deduplicated project resolution by creating a cached `resolve_project_id()` resolver in `app/config.py` and deleted duplicate blocks in other services.
- Extracted complexity helpers `_strip_fences`, `_coerce_items`, and `_render_bar` to keep Radon CC below B(6).

### Removed
- Removed merged `app/services/carbon_engine.py`.

## [1.1.0] - 2026-06-10

### Added
- Implemented typing annotations using `from __future__ import annotations` across all codebase files.
- Refactored API routes to extract `_extract_structured_items` and `_compose_track_payload`.
- Implemented cache invalidation prefix `invalidate_prefix` for insights on new tracks.
- Added unit tests to `tests/` targeting mocked Gemini APIs, Translation errors, and logging JSON formatter.
- Created `.github/workflows/ci.yml` CI config targeting Python 3.11.

### Changed
- Narrowed generic `except Exception` blocks to `UPSTREAM_FAILURES` containing Google core exceptions and credential errors.

## [1.0.0] - 2026-06-09

### Added
- Initial release of GreenPrint Carbon Footprint Awareness Platform.
- App-factory layout using Blueprint routing.
- Domain services: `CarbonIntelligenceEngine`, `EmissionFactorRegistry`, `InsightComposer`, `FootprintLedger`, `ResponseTranslator`, `ArchiveVault`, `SecretVault`, `SentimentLens`.
- Single-page application interface.
- Additive CSP, HSTS, and frame protection security headers.
