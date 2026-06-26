"""Environment-driven application configuration.

All runtime knobs are declared here and loaded via ``pydantic-settings``.
The :class:`Settings` instance is constructed lazily through
:func:`get_settings` so tests and tooling can build isolated instances
without touching module-level state.

Secrets are stored as :class:`pydantic.SecretStr`; their string
representation is redacted and never returned through the public surface.
A missing ``.env`` is not an error — the loader falls back to
process environment and defaults.

Nested configuration groups (for example the LLM block) use the
``LLM__`` style prefix resolved by ``env_nested_delimiter="__"``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Defaults — sourced from the design doc §12. Bumping a default here is a
# breaking change for operators; bump the minor version and update
# ``.env.example`` alongside.
# ---------------------------------------------------------------------------

_DEFAULT_PORT = 8000
_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_MAX_BODY_BYTES = 64 * 1024  # 64 KiB
_DEFAULT_REQUEST_TIMEOUT_MS = 30_000  # 30 s hard ceiling
_DEFAULT_LLM_ENABLED = False
_DEFAULT_LLM_TIMEOUT_MS = 1500
_DEFAULT_LLM_CACHE_SIZE = 1024
_DEFAULT_METRICS_ENABLED = False
_DEFAULT_PROFILE_ENABLED = False
_DEFAULT_OTEL_ENABLED = False


class Settings(BaseSettings):
    """Typed application configuration.

    The model is frozen at the type level (``frozen=True``) so a
    successfully-validated instance is immutable for the lifetime of the
    process. Re-configuration requires building a new instance via
    :func:`get_settings.cache_clear` then :func:`get_settings`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    # ---- Process / transport ------------------------------------------------

    port: int = Field(default=_DEFAULT_PORT, ge=1, le=65535)
    """HTTP port the ASGI server binds to."""

    log_level: str = Field(default=_DEFAULT_LOG_LEVEL, min_length=1, max_length=16)
    """Log level for structlog (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``)."""

    max_body_bytes: int = Field(
        default=_DEFAULT_MAX_BODY_BYTES,
        ge=1024,
        le=10 * 1024 * 1024,
    )
    """Maximum accepted request body size in bytes. ``413`` over the cap."""

    request_timeout_ms: int = Field(
        default=_DEFAULT_REQUEST_TIMEOUT_MS,
        ge=100,
        le=300_000,
    )
    """Hard per-request timeout in milliseconds. ``504`` on overrun."""

    # ---- Optional feature flags --------------------------------------------

    metrics_enabled: bool = Field(default=_DEFAULT_METRICS_ENABLED)
    """Expose Prometheus metrics on ``GET /metrics`` when ``True``."""

    profile_enabled: bool = Field(default=_DEFAULT_PROFILE_ENABLED)
    """Enable the optional ``cProfile`` middleware. Off by default."""

    otel_enabled: bool = Field(default=_DEFAULT_OTEL_ENABLED)
    """Enable OpenTelemetry instrumentation. Off by default."""

    # ---- Optional LLM provider ---------------------------------------------

    llm_enabled: bool = Field(default=_DEFAULT_LLM_ENABLED)
    """Feature flag for the optional LLM adapter. Default off."""

    llm_api_key: SecretStr | None = Field(default=None)
    """Provider API key. ``repr`` is redacted; never logged."""

    llm_model: str | None = Field(default=None, min_length=1, max_length=128)
    """Provider model identifier, e.g. ``gpt-4o-mini``."""

    llm_timeout_ms: int = Field(
        default=_DEFAULT_LLM_TIMEOUT_MS,
        ge=100,
        le=60_000,
    )
    """Hard timeout for a single provider call. The client falls back to
    the rule templates on overrun."""

    llm_cache_size: int = Field(default=_DEFAULT_LLM_CACHE_SIZE, ge=1, le=1_000_000)
    """Maximum number of entries in the in-process LRU cache."""

    # ---- Public helpers ----------------------------------------------------

    def shape(self) -> dict[str, Any]:
        """Return the configuration *shape* — keys with values redacted.

        Suitable for an ``INFO``-level startup log line. Secrets appear as
        ``"***"``; booleans and integers are returned as-is; ``None``
        fields are present with value ``None`` so operators can verify
        which optional knobs are set.
        """
        redacted: dict[str, Any] = {}
        for name in type(self).model_fields:
            value = getattr(self, name)
            redacted[name] = _redact(name, value)
        return redacted


def _redact(name: str, value: Any) -> Any:
    """Redact a single configuration field for safe logging."""
    if isinstance(value, SecretStr):
        return "***" if value.get_secret_value() else None
    # Heuristic: anything containing ``api_key``, ``secret``, ``password``,
    # or ``token`` is treated as sensitive even if the model did not wrap
    # it in ``SecretStr``.
    lowered = name.lower()
    if any(token in lowered for token in ("api_key", "secret", "password", "token")):
        if value is None:
            return None
        return "***"
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance.

    The function is ``lru_cache``-wrapped so callers obtain a stable
    instance for the lifetime of the process. Tests that need a fresh
    configuration should call :func:`get_settings.cache_clear` and then
    re-invoke this function under their own ``monkeypatch`` of
    ``os.environ``.
    """
    return Settings()


__all__ = ["Settings", "get_settings"]
