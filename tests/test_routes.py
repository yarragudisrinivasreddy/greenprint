"""API endpoint contracts: shapes, status codes and translation behaviour."""
from __future__ import annotations

from typing import Any


class TestTrackEndpoint:
    def test_track_with_free_text_returns_estimates(self, client: Any) -> None:
        response = client.post("/api/track", json={"text": "drove to office", "language": "en"})
        body = response.get_json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["total_kg_co2e"] > 0
        assert body["estimates"][0]["factor_key"] == "transport.car_petrol_km"

    def test_track_with_structured_activities(self, client: Any) -> None:
        response = client.post(
            "/api/track",
            json={"activities": [{"factor_key": "food.meal_veg", "quantity": 2}], "language": "en"},
        )
        body = response.get_json()
        assert body["total_kg_co2e"] == 1.4

    def test_track_includes_processing_time_metadata(self, client: Any) -> None:
        response = client.post("/api/track", json={"text": "metro ride"})
        assert "processing_time_ms" in response.get_json()

    def test_track_assigns_session_id_when_absent(self, client: Any) -> None:
        body = client.post("/api/track", json={"text": "metro"}).get_json()
        assert body["session_id"]

    def test_track_full_response_translated_for_hindi(self, client: Any) -> None:
        body = client.post("/api/track", json={"text": "drove", "language": "hi"}).get_json()
        assert body["eco_tip"].startswith("[hi]")
        assert body["estimates"][0]["label"].startswith("[hi]")
        # Machine keys stay untouched by translation.
        assert body["estimates"][0]["factor_key"] == "transport.car_petrol_km"

    def test_track_without_text_or_activities_is_400(self, client: Any) -> None:
        response = client.post("/api/track", json={"language": "en"})
        assert response.status_code == 400
        assert response.get_json()["status"] == "error"

    def test_track_with_non_json_body_is_400(self, client: Any) -> None:
        response = client.post("/api/track", data="not json", content_type="text/plain")
        assert response.status_code == 400


class TestInsightsEndpoint:
    def _seed(self, client: Any) -> str:
        body = client.post("/api/track", json={"text": "drove 10 km"}).get_json()
        return str(body["session_id"])

    def test_insights_require_session_id(self, client: Any) -> None:
        assert client.get("/api/insights").status_code == 400

    def test_insights_return_score_actions_and_svg(self, client: Any) -> None:
        session_id = self._seed(client)
        body = client.get(f"/api/insights?session_id={session_id}").get_json()
        assert 0 <= body["eco_score"]["score"] <= 100
        assert body["weekly_trend_svg"].startswith("<svg")
        assert isinstance(body["top_actions"], list)

    def test_insights_second_read_served_from_cache(self, client: Any, services: Any) -> None:
        session_id = self._seed(client)
        first = client.get(f"/api/insights?session_id={session_id}").get_json()
        services.ledger.records.clear()  # If cache works, cleared ledger is invisible.
        second = client.get(f"/api/insights?session_id={session_id}").get_json()
        assert first["summary"] == second["summary"]

    def test_cache_invalidation_regression(self, client: Any) -> None:
        track1 = client.post("/api/track", json={"text": "metro", "language": "en"}).get_json()
        session_id = track1["session_id"]

        insights1 = client.get(f"/api/insights?session_id={session_id}&language=en").get_json()
        assert insights1["summary"]["total_kg_co2e"] == 1.8

        client.post("/api/track", json={"text": "metro", "language": "en", "session_id": session_id})

        insights2 = client.get(f"/api/insights?session_id={session_id}&language=en").get_json()
        assert insights2["summary"]["total_kg_co2e"] == 3.6


class TestSimulateEndpoint:
    def test_simulate_requires_scenario(self, client: Any) -> None:
        assert client.post("/api/simulate", json={"language": "en"}).status_code == 400

    def test_simulate_projects_transport_saving(self, client: Any) -> None:
        session_body = client.post("/api/track", json={"text": "drove 20 km"}).get_json()
        response = client.post(
            "/api/simulate",
            json={"scenario": "switch commutes to metro", "session_id": session_body["session_id"]},
        ).get_json()
        assert response["matched_category"] == "transport"
        assert response["weekly_saving_kg"] > 0
        assert response["narrative"]


class TestHistoryAndFactors:
    def test_history_requires_session_id(self, client: Any) -> None:
        assert client.get("/api/history").status_code == 400

    def test_history_returns_persisted_records(self, client: Any) -> None:
        session_id = client.post("/api/track", json={"text": "metro"}).get_json()["session_id"]
        body = client.get(f"/api/history?session_id={session_id}").get_json()
        assert body["count"] == 1

    def test_factor_catalog_is_public(self, client: Any) -> None:
        body = client.get("/api/factors").get_json()
        assert "transport.metro_km" in body["factors"]

    def test_unknown_route_returns_json_404(self, client: Any) -> None:
        response = client.get("/api/nonexistent")
        assert response.status_code == 404
        assert response.get_json()["status"] == "error"
