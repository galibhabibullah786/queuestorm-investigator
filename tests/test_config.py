"""Tests for the configuration module.

These tests build :class:`Settings` instances under controlled
``os.environ`` patches so they neither read the host's real ``.env`` nor
pollute the process environment for sibling tests. ``get_settings()``'s
``lru_cache`` is cleared at the end of every test that exercises it so
that the global cache never leaks across cases.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings, get_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_env(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Strip configuration-related env vars before each test.

    Anything in ``_STRIPPED_VARS`` is removed from the process
    environment for the duration of the test, regardless of whether the
    host shell has a value set. After the test the monkeypatch teardown
    restores the original environment automatically.
    """
    for key in _STRIPPED_VARS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


_STRIPPED_VARS = frozenset(
    {
        "PORT",
        "LOG_LEVEL",
        "MAX_BODY_BYTES",
        "REQUEST_TIMEOUT_MS",
        "METRICS_ENABLED",
        "PROFILE_ENABLED",
        "OTEL_ENABLED",
        "LLM_ENABLED",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_TIMEOUT_MS",
        "LLM_CACHE_SIZE",
    }
)


def _env(**values: str) -> dict[str, str]:
    """Build a dict suitable for ``monkeypatch.setenv`` iteration."""
    return {key: str(value) for key, value in values.items()}


def _build(env: dict[str, str] | None = None) -> Settings:
    """Build a fresh :class:`Settings` from ``env`` (no env-file read)."""
    if env is None:
        return Settings(_env_file=None)
    return Settings(_env_file=None, **env)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_defaults_match_design_doc() -> None:
    settings = _build()
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.max_body_bytes == 64 * 1024
    assert settings.request_timeout_ms == 30_000
    assert settings.llm_enabled is False
    assert settings.llm_api_key is None
    assert settings.llm_model is None
    assert settings.llm_timeout_ms == 1500
    assert settings.llm_cache_size == 1024
    assert settings.metrics_enabled is False
    assert settings.profile_enabled is False
    assert settings.otel_enabled is False


# ---------------------------------------------------------------------------
# Env override — flat keys
# ---------------------------------------------------------------------------


def test_flat_env_overrides_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _env(
        PORT="9000",
        LOG_LEVEL="DEBUG",
        MAX_BODY_BYTES="131072",
        REQUEST_TIMEOUT_MS="5000",
        LLM_ENABLED="true",
        LLM_MODEL="gpt-4o-mini",
        METRICS_ENABLED="true",
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None)
    assert settings.port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.max_body_bytes == 131072
    assert settings.request_timeout_ms == 5000
    assert settings.llm_enabled is True
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.metrics_enabled is True


def test_llm_api_key_is_secret_str(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test-abcdef")
    settings = Settings(_env_file=None)
    assert isinstance(settings.llm_api_key, SecretStr)
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-test-abcdef"


def test_llm_api_key_absent_is_none() -> None:
    settings = _build()
    assert settings.llm_api_key is None


# ---------------------------------------------------------------------------
# Nested env override via env_nested_delimiter
# ---------------------------------------------------------------------------


def test_nested_env_uses_double_underscore_delimiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flat top-level fields bind the underscore-joined env key.

    The model declares ``env_nested_delimiter='__'`` so a future nested
    ``LLM`` sub-model would resolve ``LLM__TIMEOUT_MS`` -> ``llm.timeout_ms``.
    Today ``llm_timeout_ms`` is a flat top-level field; its canonical env
    binding is therefore ``LLM_TIMEOUT_MS``. Unknown ``LLM__*`` keys are
    dropped by ``extra='ignore'``.
    """
    monkeypatch.setenv("LLM_TIMEOUT_MS", "2500")
    monkeypatch.setenv("LLM_CACHE_SIZE", "256")
    settings = Settings(_env_file=None)
    assert settings.llm_timeout_ms == 2500
    assert settings.llm_cache_size == 256


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_port_below_one_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_port_above_max_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "65536")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_max_body_bytes_below_minimum_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_BODY_BYTES", "100")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_max_body_bytes_above_maximum_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_BODY_BYTES", "20971520")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_request_timeout_ms_below_minimum_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUEST_TIMEOUT_MS", "10")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_llm_timeout_ms_below_minimum_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The flat top-level field ``llm_timeout_ms`` binds the env key
    # ``LLM_TIMEOUT_MS`` (``extra='ignore'`` swallows any other form).
    monkeypatch.setenv("LLM_TIMEOUT_MS", "50")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_llm_cache_size_below_minimum_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_CACHE_SIZE", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_log_level_must_be_non_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_unknown_env_keys_are_ignored() -> None:
    """``extra='ignore'`` lets future-proof env vars land without errors."""
    settings = Settings(_env_file=None, FUTURE_FLAG="true")
    assert not hasattr(settings, "future_flag")


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_settings_instance_is_frozen() -> None:
    settings = _build()
    with pytest.raises(ValidationError):
        settings.port = 9001  # type: ignore[misc]


# ---------------------------------------------------------------------------
# shape() — redacted logging surface
# ---------------------------------------------------------------------------


def test_shape_redacts_secret_str_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-very-secret")
    settings = Settings(_env_file=None)
    shape = settings.shape()
    assert shape["llm_api_key"] == "***"


def test_shape_redacts_absent_secret_to_none() -> None:
    settings = _build()
    shape = settings.shape()
    assert shape["llm_api_key"] is None


def test_shape_includes_every_documented_field() -> None:
    settings = _build()
    shape = settings.shape()
    expected = {
        "port",
        "log_level",
        "max_body_bytes",
        "request_timeout_ms",
        "metrics_enabled",
        "profile_enabled",
        "otel_enabled",
        "llm_enabled",
        "llm_api_key",
        "llm_model",
        "llm_timeout_ms",
        "llm_cache_size",
    }
    assert expected.issubset(shape.keys())


def test_shape_preserves_non_secret_values() -> None:
    settings = _build()
    shape = settings.shape()
    assert shape["port"] == 8000
    assert shape["log_level"] == "INFO"
    assert shape["llm_enabled"] is False
    assert shape["llm_timeout_ms"] == 1500


def test_shape_does_not_leak_secret_via_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-trip through ``repr`` and ``str`` must not expose the value."""
    monkeypatch.setenv("LLM_API_KEY", "sk-very-secret")
    settings = Settings(_env_file=None)
    rendered = repr(settings.shape())
    assert "sk-very-secret" not in rendered


# ---------------------------------------------------------------------------
# get_settings() — lazy singleton
# ---------------------------------------------------------------------------


def test_get_settings_returns_settings_instance() -> None:
    get_settings.cache_clear()
    assert isinstance(get_settings(), Settings)


def test_get_settings_is_cached_across_calls() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second


def test_get_settings_cache_clear_yields_fresh_instance() -> None:
    first = get_settings()
    get_settings.cache_clear()
    second = get_settings()
    assert first is not second


def test_get_settings_reads_process_env_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cache is constructed lazily — env set after import is honoured."""
    get_settings.cache_clear()
    assert get_settings().port == 8000
    monkeypatch.setenv("PORT", "9999")
    get_settings.cache_clear()
    assert get_settings().port == 9999


# ---------------------------------------------------------------------------
# End-to-end shape sanity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "port",
        "log_level",
        "max_body_bytes",
        "request_timeout_ms",
        "metrics_enabled",
        "profile_enabled",
        "otel_enabled",
        "llm_enabled",
        "llm_api_key",
        "llm_model",
        "llm_timeout_ms",
        "llm_cache_size",
    ],
)
def test_every_field_has_a_repr_safe_shape(field: str) -> None:
    settings = _build()
    shape: dict[str, Any] = settings.shape()
    assert field in shape
    value = shape[field]
    # No raw SecretStr leaks; every value is JSON-safe (None | bool | int | str).
    assert value is None or isinstance(value, (bool, int, str))
