"""Integration coverage for privacy-safe API performance instrumentation."""

import logging
import re

from fastapi.testclient import TestClient

from backend.main import app


def test_api_response_exposes_standard_request_timing() -> None:
    """Every API response should be measurable without changing its body."""

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert re.fullmatch(r"app;dur=\d+\.\d{2}", response.headers["server-timing"])
    assert re.fullmatch(r"\d+\.\d{2}", response.headers["x-response-time-ms"])
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"


def test_request_performance_log_omits_query_values(caplog) -> None:
    """Search and role content in query strings must not enter timing logs."""

    sensitive_query = "private-candidate-search"
    with caplog.at_level(logging.INFO, logger="backend.core.performance"):
        response = TestClient(app).get(f"/api/v1/health?query={sensitive_query}")

    assert response.status_code == 200
    assert "path=/api/v1/health" in caplog.text
    assert sensitive_query not in caplog.text
