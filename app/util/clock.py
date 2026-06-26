"""Injectable wall-clock and monotonic timer.

The reasoning layer must not call :func:`datetime.now` or
:func:`time.perf_counter` directly — that would couple it to wall time
and make tests non-deterministic. Instead it depends on these two
functions, both of which can be swapped in tests via
:func:`set_clock_for_tests`.

* :func:`utc_now_iso` returns a UTC ISO-8601 string with a ``Z`` suffix.
* :func:`monotonic_ms` returns a float milliseconds value from a
  monotonic source, suitable for duration measurements.

Production default behaviour uses :func:`datetime.now` with an explicit
UTC ``tzinfo`` and :func:`time.perf_counter`. Tests typically pin both to
deterministic callables through :func:`set_clock_for_tests`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

type ClockCallable[T] = Callable[[], T]

# ---------------------------------------------------------------------------
# Defaults — overridable through ``set_clock_for_tests``
# ---------------------------------------------------------------------------


def _default_wall() -> datetime:
    return datetime.now(UTC)


_WALL_CLOCK: ClockCallable[datetime] = _default_wall
_MONOTONIC: ClockCallable[float] = time.perf_counter


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``Z`` suffix.

    Microsecond precision is preserved. Example output::

        "2026-06-26T12:34:56.789012Z"
    """
    moment = _WALL_CLOCK()
    # ``datetime.isoformat`` produces "+00:00" for UTC; the wire format the
    # service emits uses "Z" instead — normalise here so callers don't have
    # to remember to post-process.
    text = moment.isoformat()
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text


def monotonic_ms() -> float:
    """Return a monotonic millisecond reading, suitable for durations."""
    return _MONOTONIC() * 1000.0


def set_clock_for_tests(
    *,
    wall: ClockCallable[datetime] | None = None,
    mono: ClockCallable[float] | None = None,
) -> None:
    """Override the wall clock and/or monotonic source.

    Intended for tests. Pass only the sources you want to override; the
    others keep their production implementation. Call
    :func:`reset_clock` (typically in a fixture teardown) to restore
    defaults.
    """
    global _WALL_CLOCK, _MONOTONIC
    if wall is not None:
        _WALL_CLOCK = wall
    if mono is not None:
        _MONOTONIC = mono


def reset_clock() -> None:
    """Restore the production wall clock and monotonic source."""
    global _WALL_CLOCK, _MONOTONIC
    _WALL_CLOCK = _default_wall
    _MONOTONIC = time.perf_counter


__all__ = [
    "monotonic_ms",
    "reset_clock",
    "set_clock_for_tests",
    "utc_now_iso",
]
