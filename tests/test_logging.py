"""Tests for the structured logging module.

Covers the surface advertised by :mod:`app.logging`:

* :func:`configure_logging` is idempotent, emits JSON to stdout, attaches
  a ``service`` field, and respects the level filter.
* Request context round-trips through
  :func:`bind_request_context` / :func:`reset_request_context` and is
  merged into every log line.
* The redacting processors strip free-form complaint text (Plan §13.1
  "never log full complaint text") and any monetary field.
* The injectable clock in :mod:`app.util.clock` is honoured by
  ``utc_now_iso``.
"""

from __future__ import annotations

import io
import json
import logging as stdlogging
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import structlog

from app import logging as app_logging
from app.util import clock as app_clock

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_global_logging_state() -> Iterator[None]:
    """Wipe structlog and stdlib state before and after every test.

    The logging module installs a StreamHandler on the stdlib root
    logger and rewires structlog's processor chain. Tests must start
    from a clean slate so the level, formatter, and global contextvars
    don't leak between cases.
    """
    app_logging.clear_request_context()
    structlog.contextvars.clear_contextvars()
    yield
    app_logging.clear_request_context()
    structlog.contextvars.clear_contextvars()
    # Reset stdlib root logger so a misconfigured test doesn't poison
    # the next one.
    root = stdlogging.getLogger()
    root.handlers.clear()
    root.setLevel(stdlogging.WARNING)
    # Force structlog to rebuild its configuration on the next call.
    structlog.reset_defaults()


@pytest.fixture(autouse=True)
def _reset_clock() -> Iterator[None]:
    """Restore the production clock after each test."""
    yield
    app_clock.reset_clock()


def _capture_log_output(level: str = "INFO", service: str | None = None) -> io.StringIO:
    """Configure logging to write JSON into a fresh :class:`StringIO`.

    Each call re-installs structlog with the requested ``level`` and
    ``service``, then routes the new StreamHandler's stream into the
    buffer. Use ``service`` to override the default
    ``queuestorm-investigator`` name.
    """
    buffer = io.StringIO()
    if service is None:
        app_logging.configure_logging(level=level)
    else:
        app_logging.configure_logging(level=level, service=service)
    # Replace the StreamHandler's stream with our buffer so we can
    # inspect the JSON output without touching stdout.
    root = stdlogging.getLogger()
    assert root.handlers, "configure_logging did not install a handler"
    handler = root.handlers[0]
    assert isinstance(handler, stdlogging.StreamHandler)
    handler.stream = buffer
    return buffer


def _read_json_lines(buffer: io.StringIO) -> list[dict[str, object]]:
    """Return every JSON object written to ``buffer`` since last clear."""
    raw = buffer.getvalue()
    lines = [line for line in raw.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


def test_configure_logging_emits_valid_json_to_stdout() -> None:
    buffer = _capture_log_output()
    app_logging.get_logger("tests.test_logging").info("hello", request_id="abc")
    records = _read_json_lines(buffer)
    assert len(records) == 1
    record = records[0]
    assert record["event"] == "hello"
    assert record["request_id"] == "abc"
    assert record["service"] == "queuestorm-investigator"
    assert record["level"] == "info"
    assert isinstance(record["timestamp"], str)
    # The timestamp is ISO-8601 produced by structlog with utc=True.
    assert record["timestamp"].endswith("Z")


def test_configure_logging_attaches_service_field() -> None:
    buffer = _capture_log_output()
    app_logging.get_logger().info("event")
    [record] = _read_json_lines(buffer)
    assert record["service"] == "queuestorm-investigator"


def test_configure_logging_service_override() -> None:
    buffer = _capture_log_output(level="INFO", service="custom-svc")
    app_logging.get_logger().info("event")
    [record] = _read_json_lines(buffer)
    assert record["service"] == "custom-svc"


def test_configure_logging_is_idempotent() -> None:
    """Calling configure_logging twice does not raise and keeps the level."""
    app_logging.configure_logging(level="DEBUG")
    app_logging.configure_logging(level="DEBUG")  # must not raise
    assert app_logging.is_configured()
    root = stdlogging.getLogger()
    assert len(root.handlers) == 1


def test_configure_logging_unknown_level_raises() -> None:
    with pytest.raises(ValueError, match="unknown log level"):
        app_logging.configure_logging(level="LOUDER")


# ---------------------------------------------------------------------------
# Level filter
# ---------------------------------------------------------------------------


def test_level_filter_suppresses_lower_levels() -> None:
    buffer = _capture_log_output(level="INFO")
    log = app_logging.get_logger()
    log.debug("debug-event")
    log.info("info-event")
    log.warning("warning-event")
    records = _read_json_lines(buffer)
    events = [record["event"] for record in records]
    assert events == ["info-event", "warning-event"]


def test_level_filter_honors_debug() -> None:
    buffer = _capture_log_output(level="DEBUG")
    log = app_logging.get_logger()
    log.debug("debug-event")
    [record] = _read_json_lines(buffer)
    assert record["event"] == "debug-event"
    assert record["level"] == "debug"


# ---------------------------------------------------------------------------
# Request context
# ---------------------------------------------------------------------------


def test_bind_request_context_round_trips_via_token() -> None:
    token = app_logging.bind_request_context(request_id="req-1", route="/analyze-ticket")
    try:
        assert app_logging.current_request_id() == "req-1"
        assert app_logging.current_context()["route"] == "/analyze-ticket"
    finally:
        app_logging.reset_request_context(token)
    assert app_logging.current_request_id() is None


def test_bind_request_context_drops_disallowed_keys() -> None:
    """Only the documented context keys are propagated."""
    token = app_logging.bind_request_context(
        request_id="req-2",
        secret_field="leaked",  # type: ignore[arg-type]
        verdict="consistent",
    )
    try:
        context = app_logging.current_context()
        assert context["request_id"] == "req-2"
        assert context["verdict"] == "consistent"
        assert "secret_field" not in context
    finally:
        app_logging.reset_request_context(token)


def test_clear_request_context_empties_context() -> None:
    app_logging.bind_request_context(request_id="req-3")
    assert app_logging.current_request_id() == "req-3"
    app_logging.clear_request_context()
    assert app_logging.current_request_id() is None
    assert app_logging.current_context() == {}


def test_merge_request_context_attaches_to_log_records() -> None:
    buffer = _capture_log_output()
    token = app_logging.bind_request_context(
        request_id="req-4",
        route="/health",
        method="GET",
        status=200,
        duration_ms=12.5,
        case_type="refund_request",
        verdict="insufficient_data",
        severity="medium",
        llm_outcome="disabled",
    )
    try:
        app_logging.get_logger().info("handled")
    finally:
        app_logging.reset_request_context(token)
    [record] = _read_json_lines(buffer)
    assert record["request_id"] == "req-4"
    assert record["route"] == "/health"
    assert record["method"] == "GET"
    assert record["status"] == 200
    assert record["duration_ms"] == 12.5
    assert record["case_type"] == "refund_request"
    assert record["verdict"] == "insufficient_data"
    assert record["severity"] == "medium"
    assert record["llm_outcome"] == "disabled"


def test_caller_values_win_over_request_context() -> None:
    """A log line that explicitly passes ``request_id`` overrides the contextvar."""
    buffer = _capture_log_output()
    token = app_logging.bind_request_context(request_id="ctx-id")
    try:
        app_logging.get_logger().info("event", request_id="caller-id")
    finally:
        app_logging.reset_request_context(token)
    [record] = _read_json_lines(buffer)
    assert record["request_id"] == "caller-id"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_scrub_complaint_replaces_with_length_and_hash() -> None:
    """The raw text must never appear in the redacted dict."""
    raw = "I sent 5000 to 01712345678 by accident — please refund"
    record: dict[str, object] = {"complaint": raw, "case_type": "refund_request"}
    scrubbed = app_logging.scrub_complaint(stdlogging.getLogger("t"), "info", record)
    assert "complaint" not in scrubbed
    assert scrubbed["complaint_len"] == len(raw)
    assert isinstance(scrubbed["complaint_hash"], str)
    assert len(scrubbed["complaint_hash"]) == 12  # 12-char hex digest
    assert raw not in str(scrubbed)
    # The hash is a 12-char prefix of the SHA-256 hex digest, not the
    # text itself.
    assert raw[:12] != scrubbed["complaint_hash"]


def test_scrub_complaint_matches_case_insensitive_keys() -> None:
    record = {"Complaint": "secret", "Body": "another", "event": "x"}
    scrubbed = app_logging.scrub_complaint(stdlogging.getLogger("t"), "info", record)
    assert "Complaint" not in scrubbed
    assert "Body" not in scrubbed
    assert scrubbed["complaint_len"] == len("secret")
    assert scrubbed["body_len"] == len("another")


def test_scrub_complaint_drops_non_string_complaint_values() -> None:
    """A non-string under a complaint key is a programmer error; record length 0."""
    record = {"complaint": 12345}  # type: ignore[dict-item]
    scrubbed = app_logging.scrub_complaint(stdlogging.getLogger("t"), "info", record)
    assert "complaint" not in scrubbed
    assert scrubbed["complaint_len"] == 0
    assert scrubbed["complaint_hash"] == "n/a"


def test_scrub_amounts_redacts_money_keys() -> None:
    record = {
        "amount": 5000,
        "transaction_amount": "1234.56",
        "balance": 100,
        "money_sent": 42,
        "case_type": "refund_request",
    }
    scrubbed = app_logging.scrub_amounts(stdlogging.getLogger("t"), "info", record)
    assert scrubbed["amount"] == "redacted"
    assert scrubbed["transaction_amount"] == "redacted"
    assert scrubbed["balance"] == "redacted"
    assert scrubbed["money_sent"] == "redacted"
    # Unrelated keys must pass through untouched.
    assert scrubbed["case_type"] == "refund_request"


def test_scrub_amounts_matches_case_insensitive_keys() -> None:
    record = {"Transaction_Amount": 100, "Account_Balance": 50}
    scrubbed = app_logging.scrub_amounts(stdlogging.getLogger("t"), "info", record)
    assert scrubbed["Transaction_Amount"] == "redacted"
    assert scrubbed["Account_Balance"] == "redacted"


def test_full_pipeline_redacts_in_emitted_json() -> None:
    """End-to-end: a logger.info call with forbidden keys produces safe JSON."""
    buffer = _capture_log_output()
    app_logging.get_logger().info(
        "ticket_received",
        complaint="I was charged 5000 by mistake",
        amount=5000,
        case_type="payment_failed",
    )
    [record] = _read_json_lines(buffer)
    assert "complaint" not in record
    assert record["complaint_len"] == len("I was charged 5000 by mistake")
    assert record["amount"] == "redacted"
    assert record["case_type"] == "payment_failed"
    # The raw strings must never appear in the rendered JSON.
    raw_payload = json.dumps(record)
    assert "I was charged 5000 by mistake" not in raw_payload
    assert "5000" not in raw_payload  # the integer amount was redacted too


# ---------------------------------------------------------------------------
# Injectable clock
# ---------------------------------------------------------------------------


def test_utc_now_iso_returns_z_suffixed_string() -> None:
    result = app_clock.utc_now_iso()
    assert result.endswith("Z")
    # Round-trip: the stem is parseable as an ISO-8601 datetime.
    stem = result[:-1] + "+00:00"
    parsed = datetime.fromisoformat(stem)
    assert parsed.tzinfo is not None


def test_utc_now_iso_uses_injected_clock() -> None:
    fixed = datetime(2026, 6, 26, 12, 34, 56, 789012, tzinfo=UTC)
    app_clock.set_clock_for_tests(wall=lambda: fixed)
    assert app_clock.utc_now_iso() == "2026-06-26T12:34:56.789012Z"


def test_monotonic_ms_uses_injected_clock() -> None:
    samples = iter([0.0, 0.5, 1.25])
    app_clock.set_clock_for_tests(mono=lambda: next(samples))
    assert app_clock.monotonic_ms() == 0.0
    assert app_clock.monotonic_ms() == 500.0
    assert app_clock.monotonic_ms() == 1250.0


def test_reset_clock_restores_production_defaults() -> None:
    app_clock.set_clock_for_tests(wall=lambda: datetime(1970, 1, 1, tzinfo=UTC))
    app_clock.reset_clock()
    # After reset the wall clock reads "now" — far from 1970.
    value = app_clock.utc_now_iso()
    assert not value.startswith("1970")


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


def test_get_logger_returns_structlog_logger() -> None:
    logger = app_logging.get_logger("app.tests")
    # BoundLogger implements the standard log methods; ``info`` is the
    # most important one for the service.
    assert callable(logger.info)
    assert callable(logger.warning)
    assert callable(logger.error)


def test_get_logger_none_name_is_accepted() -> None:
    logger = app_logging.get_logger()
    assert callable(logger.info)
