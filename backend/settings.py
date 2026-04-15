"""
Application settings for the James Joseph Associates intelligence API.

This module defines typed configuration for the Python backend.

It gives the rest of the repository a stable way to talk about:

- the public application name
- the backend service identifier
- the API version
- the current runtime environment
- whether debug behaviour is enabled

Keeping settings in one places makes the project easier to understand because:

- `backend.main` can read app metadata from a single source
- health endpoints can report service metadata without hard-coded strings
- future Supabase, model provider, Make.com, and auth settings have a clear home
- tests can override settings in a controlled way later

In plain language:

- this module answers the question:

    "What configuration is the backend running with?"

- it should describe configuration, not business logic
- it should not connect to external services by itself

Notes
-----
- These settings use `pydantic-settings`.
- Values can come from environment variables.
- Defaults are provided for non-secret local development values.
- Secret values should never be committed to the repository.
- `.env.example` should document variable names without real secrets.

Important boundaries
--------------------
This module should not contain:

- Supabase client creation
- OpenAI or model client creation
- LangChain objects
- LangGraph workflows
- route handlers
- business logic

If a setting needs to create a real client or perform I/O, that work belongs in
a decidicated integration module, not here.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

EnvironmentName = Literal["development", "preview", "production", "test"]

class Settings(BaseSettings):
    """
    Typed runtime settings for the backend API.

    Attributes
    ----------
    app_name : str
        Human-readable application name.

        This is suitable for FastAPI metadata, generated API docs, logs, and
        developer-facing output.

    service_name : str
        Stable machine-readable service identifier.

        This is useful for health checks, monitoring, logs, deployment checks,
        and future service-to-service calls.

    api_version : str
        Current backend API version string.

        During early Phase 1 this can match the project version.

    environment : EnvironmentName
        Runtime environment name.

        This lets the backend distinguish local development, preview, production,
        and test behaviour without hard-coding environment checks through the 
        codebase.

    debug : bool
        Whether debug behaviour is enabled.

        Debug mode should stay false in production.

    Notes
    -----
    - This class only describes configuration.
    - It should not create external clients.
    - It should not validate connectivity to services.
    - More settings can be added as the backend grows.

    Environment variables
    ---------------------
    By default, these fields can be configured with:

        APP_NAME
        SERVICE_NAME
        API_VERSION
        ENVIRONMENT
        DEBUG

    Example
    -------
    A local `.env.local` or shell environment might contain:

        APP_NAME="James Joseph Associates Intelligence API"
        SERVICE_NAME="james-joseph-associates-api"
        API_VERSION="0.1.0"
        ENVIRONMENT="development"
        DEBUG="false"
    """

    # Allow configuration from environment variables while keeping defaults
    # for the first backend foundation slice
    #   - `extra="ignore"` means unrelated environment variables from Vercel,
    #     Supabase, Next.js, or the local shall will not break settings loading.
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Human-readable app name used by FastAPI metadata and generated API docs
    app_name: str = Field(
        default="James Joseph Associates Intelligence API",
        validation_alias="APP_NAME",
    )

    # Stable service identifier used by health responses and future monitoring
    service_name: str = Field(
        default="0.1.0",
        validation_alias="API_VERSION",
    )

    # Runtime environment name
    #   - Keeping this explicit now avoids scattering checks such as
    #     `if os.getenv("VERCEL_ENV") == ...` through application code later.
    environment: EnvironmentName = Field(
        default="development",
        validation_alias="ENVIRONMENT",
    )

    # Debug mode is intentionally opt-in
    #   - This should remain false for production deployments unless there is a
    #     very specific, temporary reason to enable it.
    debug: bool = Field(
        default=False,
        validation_alias="DEBUG",
    )

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the cached application settings.

    Returns
    -------
    Settings
        Typed settings loaded from defaults and environment variables.

    Notes
    -----
    - Settings are cached so the app does not repeatedly parse environment
      variables during a request.
    - Tests can clear the cache later with `get_settings.cache_clear()` if they
      need to override environment values.
    - This function does not perform network or database access.

    In plain language:

    - load settings once
    - reuse the same settings object across the app

    Example
    -------
    Import and read settings from another backend module:

        from backend.settings import get_settings

        settings = get_settings()

        print(settings.service_name)
        print(settings.api_version)

    The first call creates a `Settings` object.

    Later calls return the same cached object:

        from backend.settings import get_settings

        first = get_settings()
        second = get_settings()

        assert first is second

    This matters because settings may be read in many places, for example:

        - `backend.main`
        - `backend.api.v1.health`
        - future service modules
        - future integration modules

    In tests, the cache can be cleared if environmental variables need to be
    changed for one test case:

        from backend.settings import get_settings

        get_settings.cache_clear()

        monkeypatch.setenv("ENVIRONMENT", "test")
        settings = get_settings()

        assert settings.environment == "test"

    In plain language:

    - first call: load settings from defaults and environmental variables
    - later calls: reuse the same settings object
    - tests can clear the cache when they need a fresh settings object
    """

    return Settings()
