"""Shared pytest fixtures: app factory plus a logged-in test client."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bookmarks import create_app  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    """Fresh app with an isolated SQLite database per test."""
    application = create_app({"DATABASE": str(tmp_path / "bookmarks.db")})
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def logged_in(client):
    """Test client of a freshly registered user (session cookie set)."""
    response = client.post(
        "/api/auth/register",
        json={"username": "tester", "password": "secret123"},
    )
    assert response.status_code == 200
    return client
