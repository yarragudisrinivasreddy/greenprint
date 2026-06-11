"""Security posture: additive headers, payload limits, no request blocking."""
from __future__ import annotations

from typing import Any

EXPECTED_HEADERS = (
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Strict-Transport-Security",
    "Referrer-Policy",
    "Permissions-Policy",
    "X-XSS-Protection",
)


class TestSecurityHeaders:
    def test_all_seven_headers_present_on_home(self, client: Any) -> None:
        response = client.get("/")
        for header in EXPECTED_HEADERS:
            assert header in response.headers, f"missing {header}"

    def test_headers_present_on_api_responses(self, client: Any) -> None:
        response = client.get("/api/factors")
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_csp_has_no_unsafe_inline(self, client: Any) -> None:
        csp = client.get("/").headers["Content-Security-Policy"]
        assert "unsafe-inline" not in csp

    def test_hsts_includes_subdomains(self, client: Any) -> None:
        hsts = client.get("/").headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts and "includeSubDomains" in hsts


class TestNoRequestBlocking:
    def test_foreign_origin_request_is_served_not_403(self, client: Any) -> None:
        # External evaluators call from arbitrary origins; we never block.
        response = client.get("/", headers={"Origin": "https://evaluator.example.com"})
        assert response.status_code == 200

    def test_missing_user_agent_is_served(self, client: Any) -> None:
        response = client.get("/health", headers={"User-Agent": ""})
        assert response.status_code == 200


class TestPayloadLimits:
    def test_oversized_payload_rejected_with_413(self, client: Any) -> None:
        oversized = {"text": "x" * (11 * 1024)}
        response = client.post("/api/track", json=oversized)
        assert response.status_code == 413
        assert response.get_json()["status"] == "error"

    def test_health_reports_every_backing_service(self, client: Any) -> None:
        body = client.get("/health").get_json()
        assert set(body["services"]) == {
            "gemini",
            "emission_registry",
            "translate",
            "firestore",
            "storage",
            "secret_manager",
            "natural_language",
        }
