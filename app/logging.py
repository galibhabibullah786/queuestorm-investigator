"""Structured JSON logging for the service.

The service emits one JSON object per log line to stdout, parseable by
any log shipper without a sidecar. Configuration is intentionally
boring: a single function (:func:`configure_logging`) sets up
:class:`structlog` with a JSON renderer, ISO-8601 timestamps, a
``service`` field, and a level filter driven by configuration.

A request-scoped contextvar bag propagates correlation context
(``request_id``, ``route``, ``method``, ``status``, ``duration_ms``,
``case_type``, ``verdict``, ``severity``, ``llm_outcome``) so handlers
can attach it once and every downstream log line carries it
automatically.

Two redacting processors enforce the "no PII, no amounts, no complaint
text" rule from Plan §13.1:

* :func:`scrub_complaint` rejects keys whose value looks like a raw
  complaint (``complaint``, ``message``, ``body`` …) and replaces them
  with a length and a short hash.
* :func:`scrub_amounts` rejects any value under a key mentioning
  ``amount`` / ``balance`` / ``txn_amount`` and replaces it with
  ``"redacted"``.

Both run as the last processors before the renderer so a caller that
attempts to log the forbidden fields sees the redacted form on the wire.
"""

from __future__ import annotations

import hashlib
import logging as stdlogging
import sys
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from contextvars import ContextVar, Token
from typing import Any, cast

import structlog

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SERVICE = "queuestorm-investigator"

# Keys that may legitimately carry the raw complaint text or free-form
# user message. Any attempt to log under these names is rewritten to
# length + hash by ``scrub_complaint``.
_COMPLAINT_KEYS = frozenset(
    {"complaint", "message", "body", "text", "user_text", "raw_complaint"},
)

# Substrings that mark a field as carrying a monetary value. Matches are
# case-insensitive.
_AMOUNT_TOKENS = ("amount", "balance", "txn_amount", "money")

# Contextvar keys that downstream code is allowed to bind via
# ``bind_request_context``. Anything else is forwarded untouched by the
# context-merge processor.
_ALLOWED_CONTEXT_KEYS = frozenset(
    {
        "request_id",
        "route",
        "method",
        "status",
        "duration_ms",
        "case_type",
        "verdict",
        "severity",
        "llm_outcome",
    },
)

# ---------------------------------------------------------------------------
# Request-scoped context
# ---------------------------------------------------------------------------

# ``ContextVar`` defaults are evaluated once at module import, so a
# mutable literal would be shared between unrelated activations. We
# hold the ContextVar itself immutable (typed as ``Mapping``) and
# always replace its value with a fresh ``dict`` via ``.set(...)``.
# The literal default below is a placeholder — every read goes
# through ``.get()`` and we never mutate the returned mapping.
_request_context: ContextVar[Mapping[str, object]] = ContextVar(
    "request_context",
    default={},  # noqa: B039
)


def bind_request_context(**values: object) -> Token[Mapping[str, object]]:
    """Merge ``values`` into the request-scoped context and return a token.

    The token is intended for restoring the previous context with
    :func:`reset_request_context` once the request finishes (typically
    in middleware teardown). Keys not in :data:`_ALLOWED_CONTEXT_KEYS`
    are silently dropped so an unrelated field cannot leak into every
    log line.
    """
    current = dict(_request_context.get())
    for key, value in values.items():
        if key in _ALLOWED_CONTEXT_KEYS:
            current[key] = value
    return _request_context.set(current)


def reset_request_context(token: Token[Mapping[str, object]]) -> None:
    """Restore the context to the state captured by ``token``."""
    _request_context.reset(token)


def clear_request_context() -> None:
    """Empty the request context.

    Useful for tests; production code should pair every
    :func:`bind_request_context` with :func:`reset_request_context`.
    """
    _request_context.set({})


def current_request_id() -> str | None:
    """Return the request id bound to the current context, if any."""
    value = _request_context.get().get("request_id")
    return value if isinstance(value, str) else None


def current_context() -> Mapping[str, object]:
    """Return a read-only snapshot of the current request context."""
    return dict(_request_context.get())


# ---------------------------------------------------------------------------
# Redacting processors
# ---------------------------------------------------------------------------


def _short_hash(value: object) -> str:
    """Return a 12-character hex digest of ``value``."""
    encoded = str(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def scrub_complaint(
    _logger: stdlogging.Logger,
    _method_name: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Replace any complaint-like string with ``{length, hash}``.

    Matches are case-insensitive against :data:`_COMPLAINT_KEYS`. Non-string
    values under those keys are dropped entirely (treated as
    programmer error). The metadata keys are written using the canonical
    lowercase form (``complaint_len`` / ``complaint_hash``) regardless
    of how the offending field was spelled, so downstream log shippers
    can rely on a single, stable schema.
    """
    for key in list(event_dict):
        canonical = key.lower()
        if canonical in _COMPLAINT_KEYS:
            value = event_dict.pop(key)
            if isinstance(value, str):
                event_dict[f"{canonical}_len"] = len(value)
                event_dict[f"{canonical}_hash"] = _short_hash(value)
            else:
                event_dict[f"{canonical}_len"] = 0
                event_dict[f"{canonical}_hash"] = "n/a"
    return event_dict


def scrub_amounts(
    _logger: stdlogging.Logger,
    _method_name: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Redact any monetary-looking field to the string ``"redacted"``."""
    for key in list(event_dict):
        lowered = key.lower()
        if any(token in lowered for token in _AMOUNT_TOKENS):
            event_dict[key] = "redacted"
    return event_dict


def merge_request_context(
    _logger: stdlogging.Logger,
    _method_name: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Merge the request context into ``event_dict`` (caller values win)."""
    for key, value in _request_context.get().items():
        event_dict.setdefault(key, value)
    return event_dict


# ---------------------------------------------------------------------------
# Internal: typed adapter for the stdlib processor pipeline
# ---------------------------------------------------------------------------


# The shared processor list is typed ``list[Callable[..., object]]``
# for cleanliness, but structlog's stubs expect a stricter
# ``Sequence[Callable[[Logger, str, EventDict], EventDict]]``. The
# runtime contract is compatible — every processor we register has
# that exact signature — so we cast at the boundary.
StructlogProcessor = Callable[[Any, str, MutableMapping[str, Any]], MutableMapping[str, Any]]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_configured = False


def configure_logging(level: str = "INFO", *, service: str = _SERVICE) -> None:
    """Configure :mod:`structlog` for JSON-to-stdout output.

    Safe to call multiple times; subsequent calls reset the processor
    chain so a second ``configure_logging`` call reflects a fresh level
    or service name. The underlying stdlib root logger is silenced to
    ``WARNING`` so third-party libraries (Uvicorn, FastAPI) don't
    double-emit to stdout.
    """
    global _configured
    normalized = level.upper()
    numeric_level = stdlogging.getLevelName(normalized)
    if not isinstance(numeric_level, int):
        raise ValueError(f"unknown log level: {level!r}")

    timestamper = structlog.processors.TimeStamper(
        fmt="iso",
        utc=True,
        # ``structlog`` calls this callable once per log event. ``utc_now_iso``
        # is the production default; tests that need deterministic
        # timestamps can monkeypatch ``app.util.clock.utc_now_iso``.
    )

    shared_processors: list[Callable[..., object]] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        merge_request_context,
        timestamper,
        scrub_amounts,
        scrub_complaint,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]
    # Cast once at the boundary: structlog's stubs require a tighter
    # signature than the broader ``Callable[..., object]`` used while
    # building the list. Every entry below conforms at runtime.
    processors_typed: Sequence[StructlogProcessor] = cast(
        "Sequence[StructlogProcessor]",
        shared_processors,
    )

    structlog.configure(
        processors=processors_typed,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib-originated records (Uvicorn, FastAPI) through the same
    # JSON formatter so every log line has the same shape.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=processors_typed[:-1],
        processor=structlog.processors.JSONRenderer(),
    )
    handler = stdlogging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = stdlogging.getLogger()
    # Wipe any handlers attached by prior configuration calls or test
    # harnesses so we never end up with duplicate lines on stdout.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Bind the service field via a global contextvar so every log
    # record carries it without the caller having to remember.
    structlog.contextvars.bind_contextvars(service=service)

    _configured = True


def is_configured() -> bool:
    """Return ``True`` if :func:`configure_logging` has been called."""
    return _configured


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger.

    A ``name`` is optional; when provided it is forwarded to the stdlib
    factory so handlers that emit ``logger`` records show the right
    module path. The same name passed twice returns the same logger
    (structlog caches them).
    """
    # ``structlog.get_logger`` is typed as ``Any`` in upstream stubs;
    # runtime always returns a ``BoundLogger``.
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))


__all__ = [
    "bind_request_context",
    "clear_request_context",
    "configure_logging",
    "current_context",
    "current_request_id",
    "get_logger",
    "is_configured",
    "merge_request_context",
    "reset_request_context",
    "scrub_amounts",
    "scrub_complaint",
]
