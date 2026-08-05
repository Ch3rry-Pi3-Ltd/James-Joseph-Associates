"""Unit coverage for privacy-safe main API security helpers."""

from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.core.api_security import api_route_group, fingerprint_api_principal
from backend.db.api_security import ApiRateLimitDecision


def _request(*, headers: list[tuple[bytes, bytes]], client: str = "127.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/candidates/secret-id",
            "headers": headers,
            "client": (client, 1234),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_api_principal_fingerprint_is_stable_and_one_way() -> None:
    principal = "user_sensitive_123"
    request = _request(headers=[(b"x-workspace-user-id", principal.encode())])

    first = fingerprint_api_principal(request)
    second = fingerprint_api_principal(request)

    assert first == second
    assert len(first) == 64
    assert principal not in first


def test_api_route_group_drops_dynamic_path_values() -> None:
    assert api_route_group("/api/v1/candidates/private-candidate-id") == "candidates"
    assert "private-candidate-id" not in api_route_group(
        "/api/v1/candidates/private-candidate-id"
    )


def _secured_test_client() -> TestClient:
    from backend.core.api_security import enforce_api_security

    app = FastAPI()
    app.middleware("http")(enforce_api_security)

    @app.get("/api/v1/candidates")
    def candidates() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_deployed_api_returns_shared_rate_limit_headers() -> None:
    settings = SimpleNamespace(
        environment="production",
        api_rate_limit_enabled=True,
        api_rate_limit_per_minute=120,
    )
    decision = ApiRateLimitDecision(
        allowed=True,
        request_count=7,
        limit=120,
        retry_after_seconds=30,
    )
    with (
        patch("backend.core.api_security.get_settings", return_value=settings),
        patch("backend.core.api_security.consume_api_rate_limit", return_value=decision),
    ):
        response = _secured_test_client().get(
            "/api/v1/candidates",
            headers={"x-workspace-user-id": "user_test"},
        )

    assert response.status_code == 200
    assert response.headers["x-ratelimit-limit"] == "120"
    assert response.headers["x-ratelimit-remaining"] == "113"
    assert response.headers["cache-control"] == "private, no-store"


def test_deployed_api_rejects_exhausted_rate_limit() -> None:
    settings = SimpleNamespace(
        environment="preview",
        api_rate_limit_enabled=True,
        api_rate_limit_per_minute=2,
    )
    decision = ApiRateLimitDecision(
        allowed=False,
        request_count=2,
        limit=2,
        retry_after_seconds=41,
    )
    with (
        patch("backend.core.api_security.get_settings", return_value=settings),
        patch("backend.core.api_security.consume_api_rate_limit", return_value=decision),
    ):
        response = _secured_test_client().get("/api/v1/candidates")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "41"
    assert response.json()["error"]["code"] == "rate_limit_exceeded"


def test_deployed_api_fails_closed_when_rate_limit_database_is_unavailable() -> None:
    """A control-plane database failure must not silently disable protection."""

    settings = SimpleNamespace(
        environment="production",
        api_rate_limit_enabled=True,
        api_rate_limit_per_minute=120,
    )
    with (
        patch("backend.core.api_security.get_settings", return_value=settings),
        patch(
            "backend.core.api_security.consume_api_rate_limit",
            side_effect=RuntimeError("database unavailable"),
        ),
    ):
        response = _secured_test_client().get("/api/v1/candidates")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "rate_limit_unavailable",
            "message": "API request controls are temporarily unavailable.",
            "details": [],
        }
    }
    assert response.headers["cache-control"] == "private, no-store"
