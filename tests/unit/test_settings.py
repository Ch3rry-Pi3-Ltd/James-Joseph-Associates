"""
Unit tests for backend application settings.

This module verifies that `backend_settings` behaves predictably before more
configuration is added for Supabase, model providers, Make.com, auth, and
deployment-specific behaviour.

It gives the rest of the repository a stable way to check:

- default settings
- environment variable overrides
- cached settings behaviour
- clearing the settings cache in tests

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
- it only tests local settings behaviour
"""

from backend.settings import get_settings

def test_settings_load_default_values() -> None:
    """
    Verify that settings load safe defaults when no app-specific overrides exist.

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

    settings = get_settings()

    assert settings.app_name == "James Joseph Associates Intelligence API"
    assert settings.service_name == "james-joseph-associates-api"
    assert settings.api_version == "0.1.0"
    assert settings.environment == "development"
    assert settings.debug is False

def test_settings_can_be_overriden_from_environment(monkeypatch) -> None:
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

    settings = get_settings()

    assert settings.app_name == "Test Intelligence API"
    assert settings.service_name == "test-service"
    assert settings.api_version =="9.9.9"
    assert settings.environment == "test"
    assert settings.debug is True

    # Clear again, so later tests cannot accidentally reuse this overriden
    # setting object from the cache
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