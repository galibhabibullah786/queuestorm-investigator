"""Smoke tests — verify the app factory works.

A single assertion that `create_app()` returns a FastAPI instance
with the expected `title` and `version`. Expanded later.
"""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.main import create_app


def test_app_factory() -> None:
    """create_app() returns a FastAPI with the expected metadata."""
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "queuestorm-investigator"
    assert app.version == __version__


def test_app_factory_is_fresh() -> None:
    """create_app() returns a fresh instance each call (no module-level state)."""
    a = create_app()
    b = create_app()
    assert a is not b
