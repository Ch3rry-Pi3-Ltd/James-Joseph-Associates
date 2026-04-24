"""
Unit tests for backend application settings.

This module verifies that `backend.settings` behaves predictably before more
configuration is added for Supabase, model providers, auth, and
deployment-specific behaviour.

It gives the rest of the repository a stable way to check:

- default settings
- environment variable overrides
- cached settings behaviour
- clearing the settings cache in tests
- Postgres connection string loading
- Make.com API token loading
- JobAdder OAuth setting loading

Keeping these tests small makes the configuration layer easier to trust because:

- `backend.main` reads app metadata from settings
- `backend.api.v1.health` reads service metadata from settings
- future integration modules will depend on settings for credentials and URLs
- tests can prove configuration behaviour without connecting to external systems

In plain language:

- this module answers the question:

    "Can the backend load typed configuration reliably?"

- it does not test Supabase
- it does not test Vercel
- it does not test LangChain or LangGraph
- it does not use a real Make.com token
- it only tests local settings behaviour
"""

from backend.settings import get_settings


def test_settings_load_default_values(monkeypatch) -> None:
    """
    Verify that settings load safe defaults when no app-specific overrides exist.

    Parameters
    ----------
    monkeypatch
        Pytest fixture used to override environment variables for this test.

    Notes
    -----
    - These defaults are non-secret.
    - They let the backend run locally without requiring every future environment
      variable to exist on day one.
    - This test confirms the baseline values used by `backend.main` and the
      health endpoint.

    In plain language:

    - clea the settings cache
    - load settings
    - check the default app metadata is correct
    """

    # `get_settings()` is cached.
    #   - To make this test independent of any previous settings access, clear the
    #     cache before loading defaults.
    get_settings.cache_clear()

    # Force the database URLs to the unconfigured default for this test.
    #   - Local `.env.local` values may contain real Supabase/Postgres URLs.
    #   - Environment variables override values loaded from `.env.local`.
    monkeypatch.setenv("POSTGRES_URL_NON_POOLING", "")
    monkeypatch.setenv("POSTGRES_URL", "")
    monkeypatch.setenv("JOBADDER_CLIENT_ID", "")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "")
    monkeypatch.setenv("JOBADDER_REDIRECT_URI", "")

    settings = get_settings()

    assert settings.app_name == "James Joseph Associates Intelligence API"
    assert settings.service_name == "james-joseph-associates-api"
    assert settings.api_version == "0.1.0"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.postgres_url == ""
    assert settings.jobadder_client_id == ""
    assert settings.jobadder_client_secret == ""
    assert settings.jobadder_redirect_uri == ""


def test_settings_can_be_overridden_from_environment(monkeypatch) -> None:
    """
    Verify that app-specific environment variables override defaults.

    Parameters
    ----------
    monkeypatch
        Pytest fixture used to safely set environment variables used for this test.

    Notes
    -----
    - The settings cache is cleared before reading overridden values.
    - This matters because `get_settings()` uses `lru_cache`.
    - Without clearing the cache, the test could accidentally reuse settings
      created by a previous test.
    - `monkeypatch` restores environment changes after the test finishes.

    In plain language:

    - clear the settings cache
    - set fake environment variables
    - load settings
    - check that the fake values were used
    """

    get_settings.cache_clear()

    # These are fake app-specific values
    #   - They prove that environment variables can override the defaults without
    #     requiring real secrets or external services.
    monkeypatch.setenv("APP_NAME", "Test Intelligence API")
    monkeypatch.setenv("SERVICE_NAME", "test-service")
    monkeypatch.setenv("API_VERSION", "9.9.9")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv(
        "POSTGRES_URL_NON_POOLING",
        "postgresql://user:pass@localhost:5432/jja",
    )
    monkeypatch.setenv(
        "POSTGRES_URL",
        "postgresql://ignored:ignored@localhost:5432/ignored",
    )
    monkeypatch.setenv("MAKE_API_TOKEN", "fake-make-token")
    monkeypatch.setenv("JOBADDER_CLIENT_ID", "fake-jobadder-client-id")
    monkeypatch.setenv("JOBADDER_CLIENT_SECRET", "fake-jobadder-client-secret")
    monkeypatch.setenv(
        "JOBADDER_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/integrations/jobadder/callback",
    )

    settings = get_settings()

    assert settings.app_name == "Test Intelligence API"
    assert settings.service_name == "test-service"
    assert settings.api_version == "9.9.9"
    assert settings.environment == "test"
    assert settings.debug is True
    assert settings.postgres_url == "postgresql://user:pass@localhost:5432/jja"
    assert settings.make_api_token == "fake-make-token"
    assert settings.jobadder_client_id == "fake-jobadder-client-id"
    assert settings.jobadder_client_secret == "fake-jobadder-client-secret"
    assert (
        settings.jobadder_redirect_uri
        == "http://127.0.0.1:8000/api/v1/integrations/jobadder/callback"
    )

    # Clear again, so later tests cannot accidentally reuse this overridden
    # setting object from the cache
    get_settings.cache_clear()


def test_make_api_token_defaults_to_empty_string(monkeypatch) -> None:
    """
    Verify that `MAKE_API_TOKEN` can safely be empty.

    The Make.com token is a secret value.

    In production, Vercel should provide it as an environment variable.

    In local development and tests, it is useful for the value to default to an
    empty string so protected Make.com endpoints fail closed instead of
    accidentally accepting requests.

    Parameters
    ----------
    monkeypatch
        Pytest fixture used to override environment variables for this test.

    Notes
    -----
    - This test does not use a real Make.com token.
    - It deliberately sets the environment value to an empty string.
    - That mirrors the safe "not configured yet" state.
    - The protected Make.com endpoint checks for this and returns HTTP 401.

    In plain language:

    - no configured Make.com token
    - settings loads an empty string
    - protected Make.com routes should reject requests
    """

    get_settings.cache_clear()

    # Force the token to be empty for this test.
    #   - This avoids accidentally reading a real local token from `.env.local`.
    #   - Environment variables override values loaded from `.env.local`.
    monkeypatch.setenv("MAKE_API_TOKEN", "")

    settings = get_settings()

    assert settings.make_api_token == ""

    get_settings.cache_clear()


def test_settings_prefer_non_pooling_postgres_url(monkeypatch) -> None:
    """
    Verify that the backend prefers `POSTGRES_URL_NON_POOLING` when both exist.

    Notes
    -----
    - Supabase/Vercel may provide multiple Postgres URLs.
    - The backend should prefer the non-pooling URL for direct `psycopg`
      connections.
    - This avoids accidentally choosing a URL with extra query parameters or
      pooling behaviour that does not fit the current DB layer.
    """

    get_settings.cache_clear()

    monkeypatch.setenv(
        "POSTGRES_URL_NON_POOLING",
        "postgresql://preferred:pass@localhost:5432/jja",
    )
    monkeypatch.setenv(
        "POSTGRES_URL",
        "postgresql://fallback:pass@localhost:5432/jja",
    )

    settings = get_settings()

    assert settings.postgres_url == "postgresql://preferred:pass@localhost:5432/jja"

    get_settings.cache_clear()


def test_settings_are_cached() -> None:
    """
    Verify that repeated calls return the same settings object.

    Notes
    -----
    - The application may call `get_settings()` from multiple modules.
    - Caching avoids reparsing environment values every time.
    - This is useful for route handlers and future service/integration modules.

    In plain language:

    - clear the cache
    - call `get_settings()` twice
    - confirm both calls return the same
    """

    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    # `is` checks object identity, not just equality
    #   - This proves the second call reused the cached setting object instead of
    #     creating a new one.
    assert first is second
