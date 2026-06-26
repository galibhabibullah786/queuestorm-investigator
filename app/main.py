"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__


def create_app() -> FastAPI:
    """Return a FastAPI app instance.

    Importable without side effects so tests can build a fresh app per test.
    """
    return FastAPI(
        title="queuestorm-investigator",
        version=__version__,
    )
