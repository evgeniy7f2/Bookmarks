"""API tests: auth, groups, bookmarks, settings, export.

Run from the project root:  python -m pytest tests/ -v
"""

from __future__ import annotations

import json
import os
import re
from datetime import timedelta

import pytest

from bookmarks import api as bookmarks_api
from bookmarks import ratelimit
from bookmarks.util import FetchError, assert_fetchable, iso, parse_iso, utcnow

# ---------------------------------------------------------------------------
# Health & auth
# ---------------------------------------------------------------------------


def test_csrf_cross_site_header_rejected(logged_in):
    # No Origin, no Sec-Fetch-Site (curl-style) still works.
    direct = logged_in.post("/api/bookmarks", json={"url": "https://csrf.example/"})
    assert direct.status_code == 201
    # A browser that labels the request cross-site is rejected even
    # without an Origin header.
    cross = logged_in.post(
        "/api/bookmarks",
        json={"url": "https://csrf.example/"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert cross.status_code == 403
    # Same-origin requests pass.
    same = logged_in.post(
        "/api/bookmarks",
        json={"url": "https://csrf-same.example/"},
        headers={"Sec-Fetch-Site": "same-origin"},
    )
    assert same.status_code == 201


def test_expired_sessions_purged_on_login(client):
    assert (
        client.post(
            "/api/auth/register", json={"username": "purge", "password": "secret123"}
        ).status_code
        == 200
    )
    from bookmarks.db import get_db

    with client.application.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (
                "ancient",
                1,
                iso(utcnow() - timedelta(days=40)),
                iso(utcnow() - timedelta(days=10)),
            ),
        )
        db.commit()
    assert (
        client.post("/api/auth/login", json={"username": "purge", "password": "secret123"}).status_code
        == 200
    )
    with client.application.app_context():
        db = get_db()
        assert (
            db.execute("SELECT COUNT(*) c FROM sessions WHERE token_hash = ?", ("ancient",))
            .fetchone()["c"]
            == 0
        )


def test_expired_sessions_purged_on_startup(client):
    from bookmarks import create_app
    from bookmarks.db import get_db

    assert (
        client.post(
            "/api/auth/register", json={"username": "boot", "password": "secret123"}
        ).status_code
        == 200
    )
    database = client.application.config["DATABASE"]
    with client.application.app_context():
        db = get_db()
        db.execute(
            "UPDATE sessions SET expires_at = ?", (iso(utcnow() - timedelta(days=1)),)
        )
        db.commit()
    # A fresh application on the same database must not keep the old rows.
    restarted = create_app({"DATABASE": database})
    with restarted.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) c FROM sessions").fetchone()["c"] == 0


def test_disabled_user_is_locked_out(client):
    assert (
        client.post(
            "/api/auth/register", json={"username": "locked", "password": "secret123"}
        ).status_code
        == 200
    )
    from bookmarks.db import get_db

    with client.application.app_context():
        db = get_db()
        db.execute("UPDATE users SET disabled = 1 WHERE username = ?", ("locked",))
        db.commit()

    # An already-open session stops working at once.
    assert client.get("/api/groups").status_code == 401
    # And login is refused with a distinct code.
    denied = client.post(
        "/api/auth/login", json={"username": "locked", "password": "secret123"}
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"] == "user_disabled"

    # Unlocking (as manage.py unlock-user does) restores access.
    with client.application.app_context():
        db = get_db()
        db.execute("UPDATE users SET disabled = 0 WHERE username = ?", ("locked",))
        db.commit()
    assert (
        client.post("/api/auth/login", json={"username": "locked", "password": "secret123"}).status_code
        == 200
    )


def test_manage_reset_password_roundtrip(tmp_path):
    """manage.py reset-password must be accepted by the API afterwards."""
    import subprocess
    import sys
    from pathlib import Path

    from bookmarks import create_app

    root = Path(__file__).resolve().parents[1]
    data_dir = tmp_path / "data"
    application = create_app({"DATABASE": str(data_dir / "bookmarks.db")})
    with application.app_context():
        pass
    client = application.test_client()
    assert (
        client.post(
            "/api/auth/register", json={"username": "resetme", "password": "secret123"}
        ).status_code
        == 200
    )

    env = dict(os.environ, BOOKMARKS_DATA=str(data_dir))
    result = subprocess.run(
        [sys.executable, str(root / "manage.py"), "reset-password", "resetme", "brandnew123"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # Old password no longer works, the new one does.
    assert (
        client.post(
            "/api/auth/login", json={"username": "resetme", "password": "secret123"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"username": "resetme", "password": "brandnew123"}
        ).status_code
        == 200
    )


def test_manage_backup_roundtrip(tmp_path):
    """manage.py backup must produce a readable copy with the same data."""
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    from bookmarks import create_app

    root = Path(__file__).resolve().parents[1]
    data_dir = tmp_path / "data"
    application = create_app({"DATABASE": str(data_dir / "bookmarks.db")})
    with application.app_context():
        pass
    client = application.test_client()
    assert (
        client.post(
            "/api/auth/register", json={"username": "backme", "password": "secret123"}
        ).status_code
        == 200
    )
    assert (
        client.post("/api/bookmarks", json={"url": "https://example.com/backup"}).status_code
        == 201
    )

    target = tmp_path / "out" / "backup.sqlite3"
    env = dict(os.environ, BOOKMARKS_DATA=str(data_dir))
    result = subprocess.run(
        [sys.executable, str(root / "manage.py"), "backup", str(target)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert target.exists()

    check = sqlite3.connect(target)
    try:
        users = check.execute("SELECT username FROM users").fetchall()
        links = check.execute("SELECT url FROM bookmarks").fetchall()
    finally:
        check.close()
    assert ("backme",) in users
    assert any(url.startswith("https://example.com/backup") for (url,) in links)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["db"] is True


def test_health_reports_broken_database(tmp_path):
    from bookmarks import create_app

    database = tmp_path / "bookmarks.db"
    application = create_app({"DATABASE": str(database)})
    database.write_bytes(b"this is not a sqlite database file at all")
    response = application.test_client().get("/health")
    assert response.status_code == 503
    body = response.get_json()
    assert body["ok"] is False
    assert body["db"] is False


def test_index_requires_nothing_but_is_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]
    assert "Bookmarks" in response.get_data(as_text=True)


def test_api_requires_auth(client):
    for path in ("/api/groups", "/api/bookmarks", "/api/export"):
        assert client.get(path).status_code == 401


def test_register_success(logged_in, client):
    me = client.get("/api/auth/me").get_json()["user"]
    assert me["username"] == "tester"
    # Default Favorites and Secret groups are created on registration,
    # Secret always right after Favorites.
    groups = client.get("/api/groups").get_json()["groups"]
    assert [group["kind"] for group in groups] == ["favorites", "secret"]
    assert groups[1]["unlocked"] is True
    assert groups[1]["password_set"] is False


def test_register_validation_errors(client):
    weak = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "123"},
    )
    assert weak.status_code == 400
    assert weak.get_json()["error"] == "weak_password"

    bad_name = client.post(
        "/api/auth/register",
        json={"username": "a b!", "password": "secret123"},
    )
    assert bad_name.status_code == 400
    assert bad_name.get_json()["error"] == "invalid_username"

    first = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "secret123"},
    )
    assert first.status_code == 200
    taken = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "other456"},
    )
    assert taken.status_code == 409
    assert taken.get_json()["error"] == "username_taken"


def test_login_logout_flow(client):
    client.post(
        "/api/auth/register",
        json={"username": "bob", "password": "secret123"},
    )
    client.post("/api/auth/logout")

    wrong = client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "nope123"},
    )
    assert wrong.status_code == 401
    assert wrong.get_json()["error"] == "invalid_credentials"

    ok = client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "secret123"},
    )
    assert ok.status_code == 200
    assert ok.get_json()["user"]["username"] == "bob"

    assert client.post("/api/auth/logout").status_code == 200
    # After logout the session cookie is cleared.
    assert client.get("/api/auth/me").get_json()["user"] is None
    assert client.get("/api/groups").status_code == 401


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def test_groups_crud(logged_in):
    created = logged_in.post("/api/groups", json={"name": "Dev", "icon": "🧪"})
    assert created.status_code == 201
    group = created.get_json()["group"]
    assert group["name"] == "Dev"
    assert group["icon"] == "🧪"
    assert group["kind"] == "custom"

    renamed = logged_in.patch(f"/api/groups/{group['id']}", json={"name": "Dev2"})
    assert renamed.status_code == 200
    assert renamed.get_json()["group"]["name"] == "Dev2"

    deleted = logged_in.delete(f"/api/groups/{group['id']}")
    assert deleted.status_code == 200
    assert deleted.get_json()["ok"] is True

    remaining = [
        row["id"] for row in logged_in.get("/api/groups").get_json()["groups"]
    ]
    assert group["id"] not in remaining


def test_favorites_group_is_locked(logged_in):
    favorites = next(
        row
        for row in logged_in.get("/api/groups").get_json()["groups"]
        if row["kind"] == "favorites"
    )
    assert logged_in.delete(f"/api/groups/{favorites['id']}").status_code == 400
    assert (
        logged_in.patch(f"/api/groups/{favorites['id']}", json={"name": "x"})
        .status_code
        == 400
    )


def test_secret_group_is_locked(logged_in):
    groups = logged_in.get("/api/groups").get_json()["groups"]
    secret = next(row for row in groups if row["kind"] == "secret")
    # Name and icon are fixed, and the group cannot be deleted (like
    # Favorites) — only its password changes.
    assert (
        logged_in.patch(f"/api/groups/{secret['id']}", json={"name": "x"})
        .status_code
        == 400
    )
    assert (
        logged_in.patch(f"/api/groups/{secret['id']}", json={"icon": "🗝"})
        .status_code
        == 400
    )
    assert logged_in.delete(f"/api/groups/{secret['id']}").status_code == 400


def test_secret_password_flow(logged_in):
    groups = logged_in.get("/api/groups").get_json()["groups"]
    secret = next(row for row in groups if row["kind"] == "secret")
    secret_id = secret["id"]

    # Setting the password: too short is rejected.
    short = logged_in.patch(f"/api/groups/{secret_id}", json={"password": "ab"})
    assert short.status_code == 400
    assert short.get_json()["error"] == "secret_password_short"

    # A link in the Secret group is invisible on the home feed (created
    # before the password is set, since a closed group refuses new links).
    created = logged_in.post(
        "/api/bookmarks",
        json={"url": "https://secret.example/", "title": "Hidden", "group_id": secret_id},
    )
    assert created.status_code == 201
    link_id = created.get_json()["bookmark"]["id"]

    ok = logged_in.patch(f"/api/groups/{secret_id}", json={"password": "s3cret12"})
    assert ok.status_code == 200
    assert ok.get_json()["group"]["password_set"] is True
    # After setting a password the group is locked again.
    assert ok.get_json()["group"]["unlocked"] is False

    home = logged_in.get("/api/bookmarks").get_json()["bookmarks"]
    assert all(row["id"] != link_id for row in home)

    # Locked: the group view is empty, wrong password is rejected.
    assert (
        logged_in.get(f"/api/bookmarks?group_id={secret_id}").get_json()["bookmarks"]
        == []
    )
    wrong = logged_in.post(
        f"/api/groups/{secret_id}/unlock", json={"password": "wrong"}
    )
    assert wrong.status_code == 400
    assert wrong.get_json()["error"] == "wrong_password"

    ok = logged_in.post(
        f"/api/groups/{secret_id}/unlock", json={"password": "s3cret12"}
    )
    assert ok.status_code == 200
    secret_after = next(
        row
        for row in logged_in.get("/api/groups").get_json()["groups"]
        if row["id"] == secret_id
    )
    assert secret_after["unlocked"] is True
    links = logged_in.get(f"/api/bookmarks?group_id={secret_id}").get_json()["bookmarks"]
    assert [row["id"] for row in links] == [link_id]
    # Still not on the home feed while unlocked.
    home = logged_in.get("/api/bookmarks").get_json()["bookmarks"]
    assert all(row["id"] != link_id for row in home)

    # Re-lock (clicking the open icon): the links disappear again.
    assert logged_in.post(f"/api/groups/{secret_id}/lock").status_code == 200
    assert (
        logged_in.get(f"/api/bookmarks?group_id={secret_id}").get_json()["bookmarks"]
        == []
    )

    # Unlock once more, then remove the password: the group becomes open.
    logged_in.post(f"/api/groups/{secret_id}/unlock", json={"password": "s3cret12"})
    opened = logged_in.patch(f"/api/groups/{secret_id}", json={"password": ""})
    assert opened.status_code == 200
    assert opened.get_json()["group"]["password_set"] is False
    assert opened.get_json()["group"]["unlocked"] is True
    links = logged_in.get(f"/api/bookmarks?group_id={secret_id}").get_json()["bookmarks"]
    assert [row["id"] for row in links] == [link_id]
    no_password = logged_in.post(
        f"/api/groups/{secret_id}/unlock", json={"password": "s3cret12"}
    )
    assert no_password.status_code == 400
    assert no_password.get_json()["error"] == "secret_no_password"


def test_home_still_shows_ungrouped_and_custom(logged_in):
    # Regression: excluding the secret group from general feeds must not
    # drop links whose group_id is NULL (ungrouped) or a custom group.
    groups = logged_in.get("/api/groups").get_json()["groups"]
    secret = next(row for row in groups if row["kind"] == "secret")

    custom = logged_in.post("/api/groups", json={"name": "Work"}).get_json()["group"]

    secret_link = logged_in.post(
        "/api/bookmarks", json={"url": "https://s.example/", "title": "S", "group_id": secret["id"]}
    ).get_json()["bookmark"]
    assert logged_in.patch(
        f"/api/groups/{secret['id']}", json={"password": "s3cret12"}
    ).status_code == 200
    ungrouped = logged_in.post(
        "/api/bookmarks", json={"url": "https://u.example/", "title": "U"}
    ).get_json()["bookmark"]
    custom_link = logged_in.post(
        "/api/bookmarks", json={"url": "https://w.example/", "title": "W", "group_id": custom["id"]}
    ).get_json()["bookmark"]

    home_ids = [row["id"] for row in logged_in.get("/api/bookmarks").get_json()["bookmarks"]]
    assert ungrouped["id"] in home_ids
    assert custom_link["id"] in home_ids
    assert secret_link["id"] not in home_ids


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------


def test_bookmarks_crud(logged_in):
    created = logged_in.post(
        "/api/bookmarks",
        json={
            "url": "https://example.com/",
            "title": "Example",
            "description": "notes",
            "tags": ["web", "test"],
        },
    )
    assert created.status_code == 201
    bookmark = created.get_json()["bookmark"]
    assert bookmark["title"] == "Example"
    assert sorted(bookmark["tags"]) == ["test", "web"]

    # The same URL is a duplicate for this user.
    duplicate = logged_in.post("/api/bookmarks", json={"url": "https://example.com/"})
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"] == "duplicate"

    updated = logged_in.patch(
        f"/api/bookmarks/{bookmark['id']}", json={"title": "Example 2"}
    )
    assert updated.status_code == 200
    assert updated.get_json()["bookmark"]["title"] == "Example 2"

    # Favorite toggle creates a copy inside the Favorites group.
    favorited = logged_in.post(f"/api/bookmarks/{bookmark['id']}/favorite")
    assert favorited.status_code == 200
    assert favorited.get_json()["favorited"] is True

    deleted = logged_in.delete(f"/api/bookmarks/{bookmark['id']}")
    assert deleted.status_code == 200
    assert deleted.get_json()["ok"] is True

    listed = [
        row["id"]
        for row in logged_in.get("/api/bookmarks").get_json()["bookmarks"]
    ]
    assert bookmark["id"] not in listed

    restored = logged_in.post(f"/api/bookmarks/{bookmark['id']}/restore")
    assert restored.status_code == 200
    assert restored.get_json()["bookmark"]["deleted_at"] is None


def test_bookmark_not_found(logged_in):
    assert logged_in.get("/api/bookmarks/9999").status_code == 404
    assert logged_in.delete("/api/bookmarks/9999").status_code == 404


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_roundtrip(logged_in):
    updated = logged_in.put("/api/settings", json={"lang": "en", "theme": "nord"})
    assert updated.status_code == 200
    assert updated.get_json()["settings"]["lang"] == "en"
    assert updated.get_json()["settings"]["theme"] == "nord"

    # "dark" is a color scheme, not a theme name — it must land in colorScheme.
    updated = logged_in.put("/api/settings", json={"theme": "dark"})
    assert updated.get_json()["settings"]["theme"] == "nord"
    assert updated.get_json()["settings"]["colorScheme"] == "dark"

    current = logged_in.get("/api/settings").get_json()["settings"]
    assert current["lang"] == "en"
    assert current["theme"] == "nord"
    assert current["colorScheme"] == "dark"


def test_settings_quicklinks(logged_in):
    # Up to five entries are kept; junk and overflow are dropped.
    links = [{"url": f"https://example.com/{i}", "title": f"Link {i}"} for i in range(7)]
    updated = logged_in.put("/api/settings", json={"quicklinks": links})
    assert updated.status_code == 200
    saved = updated.get_json()["settings"]["quicklinks"]
    assert len(saved) == 5
    assert saved[0] == {"url": "https://example.com/0", "title": "Link 0", "icon": None}

    # Entries without a usable url and empty lists are normalized away.
    updated = logged_in.put(
        "/api/settings",
        json={"quicklinks": [{"title": "no url"}, "not a dict", {"url": "https://a.b"}]},
    )
    assert updated.get_json()["settings"]["quicklinks"] == [
        {"url": "https://a.b", "title": "", "icon": None}
    ]

    # A valid image icon is kept; a bogus one is dropped back to the favicon.
    png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    updated = logged_in.put(
        "/api/settings",
        json={
            "quicklinks": [
                {"url": "https://a.b", "title": "A", "icon": png},
                {"url": "https://c.d", "icon": "not-an-image"},
            ]
        },
    )
    saved = updated.get_json()["settings"]["quicklinks"]
    assert saved[0] == {"url": "https://a.b", "title": "A", "icon": png}
    assert saved[1] == {"url": "https://c.d", "title": "", "icon": None}

    current = logged_in.get("/api/settings").get_json()["settings"]
    assert current["quicklinks"] == saved


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_netscape_export_add_date_matches_created_at(logged_in):
    favorites = next(
        row
        for row in logged_in.get("/api/groups").get_json()["groups"]
        if row["kind"] == "favorites"
    )
    created = logged_in.post(
        "/api/bookmarks",
        json={
            "url": "https://example.org/",
            "title": "Example Org",
            "group_id": favorites["id"],
        },
    )
    assert created.status_code == 201
    bookmark = created.get_json()["bookmark"]

    response = logged_in.get("/api/export?format=html")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "NETSCAPE-Bookmark-file-1" in html
    assert "Example Org" in html

    match = re.search(r'ADD_DATE="(\d+)"', html)
    assert match is not None
    expected = int(parse_iso(bookmark["created_at"]).timestamp())
    assert int(match.group(1)) == expected


def test_json_export(logged_in):
    logged_in.post(
        "/api/bookmarks",
        json={"url": "https://example.net/", "title": "Example Net"},
    )
    response = logged_in.get("/api/export")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["app"] == "Bookmarks"
    assert any(row["url"] == "https://example.net/" for row in payload["bookmarks"])


def test_html_export_keeps_ungrouped_links(logged_in):
    created = logged_in.post(
        "/api/bookmarks",
        json={"url": "https://ungrouped.example/", "title": "Ungrouped link"},
    )
    assert created.status_code == 201

    html = logged_in.get("/api/export?format=html").get_data(as_text=True)
    assert "Ungrouped link" in html
    assert "https://ungrouped.example/" in html
    assert "<H3>Unsorted</H3>" in html


def test_group_names_are_unique(logged_in):
    first = logged_in.post("/api/groups", json={"name": "Work"})
    assert first.status_code == 201
    first_id = first.get_json()["group"]["id"]

    dup = logged_in.post("/api/groups", json={"name": "wOrK"})
    assert dup.status_code == 409
    assert dup.get_json()["error"] == "group_name_taken"

    for name in ("Favorites", "secret"):
        reserved = logged_in.post("/api/groups", json={"name": name})
        assert reserved.status_code == 409
        assert reserved.get_json()["error"] == "group_name_reserved"

    second = logged_in.post("/api/groups", json={"name": "Workshop"})
    assert second.status_code == 201
    second_id = second.get_json()["group"]["id"]
    clash = logged_in.patch(f"/api/groups/{second_id}", json={"name": "work"})
    assert clash.status_code == 409
    assert clash.get_json()["error"] == "group_name_taken"
    # A name that is no longer taken is fine.
    freed = logged_in.patch(f"/api/groups/{first_id}", json={"name": "Workshop"})
    assert freed.status_code == 409
    assert (
        logged_in.patch(f"/api/groups/{first_id}", json={"name": "Woke"}).status_code == 200
    )


def test_group_name_migration_deduplicates(tmp_path):
    """Old databases with duplicate names get a ' (2)' suffix."""
    from bookmarks import create_app
    from bookmarks.db import _migrate_unique_group_names, connect

    path = str(tmp_path / "dup.db")
    connection = connect(path)
    connection.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, display_name TEXT,"
        " password_hash TEXT, avatar_color TEXT, settings TEXT, created_at TEXT)"
    )
    connection.execute(
        "CREATE TABLE groups (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT,"
        " icon TEXT, kind TEXT, position INTEGER, password_hash TEXT, created_at TEXT)"
    )
    connection.execute("INSERT INTO users VALUES (1, 'a', 'a', 'h', '#000', '{}', 'x')")
    connection.execute("INSERT INTO groups VALUES (1, 1, 'Work', '📁', 'custom', 1, NULL, 'x')")
    connection.execute("INSERT INTO groups VALUES (2, 1, 'work', '📁', 'custom', 2, NULL, 'x')")
    connection.execute("INSERT INTO groups VALUES (3, 1, 'work', '📁', 'custom', 3, NULL, 'x')")
    connection.commit()
    _migrate_unique_group_names(connection)
    names = [
        row["name"]
        for row in connection.execute("SELECT name FROM groups WHERE user_id = 1 ORDER BY id")
    ]
    connection.close()
    assert sorted(names) == ["Work", "Work (2)", "Work (3)"]


# ---------------------------------------------------------------------------
# Secret group isolation
# ---------------------------------------------------------------------------


def _groups_by_kind(client) -> dict:
    return {row["kind"]: row for row in client.get("/api/groups").get_json()["groups"]}


def _protect_secret(client, password: str = "s3cret12") -> dict:
    secret = _groups_by_kind(client)["secret"]
    response = client.patch(f"/api/groups/{secret['id']}", json={"password": password})
    assert response.status_code == 200
    return secret


def test_secret_group_hides_links_by_id(logged_in):
    secret = _groups_by_kind(logged_in)["secret"]
    created = logged_in.post(
        "/api/bookmarks",
        json={
            "url": "https://hidden.example/",
            "title": "Hidden link",
            "tags": ["private"],
            "group_id": secret["id"],
        },
    )
    assert created.status_code == 201
    link_id = created.get_json()["bookmark"]["id"]
    _protect_secret(logged_in)

    # Closed group: every by-id route behaves as if the link is missing.
    assert logged_in.get(f"/api/bookmarks/{link_id}").status_code == 404
    assert (
        logged_in.patch(f"/api/bookmarks/{link_id}", json={"title": "leak"}).status_code
        == 404
    )
    assert logged_in.delete(f"/api/bookmarks/{link_id}").status_code == 404
    assert logged_in.post(f"/api/bookmarks/{link_id}/favorite").status_code == 404
    assert logged_in.get(f"/go/{link_id}").status_code == 404

    # Search, tags, counters and the group itself must not reveal it.
    found = logged_in.get("/api/bookmarks?q=Hidden").get_json()["bookmarks"]
    assert all(row["id"] != link_id for row in found)
    tags = [row["name"] for row in logged_in.get("/api/tags").get_json()["tags"]]
    assert "private" not in tags
    stats = logged_in.get("/api/stats").get_json()
    assert stats["bookmarks"] == 0
    assert stats["tags"] == 0
    assert _groups_by_kind(logged_in)["secret"]["count"] == 0

    # Neither export format leaks the group or its links.
    for path in ("/api/export", "/api/export?format=html"):
        assert "hidden.example" not in logged_in.get(path).get_data(as_text=True)
    payload = logged_in.get("/api/export").get_json()
    assert all(row["kind"] != "secret" for row in payload["groups"])


def test_locked_secret_rejects_new_links(logged_in):
    secret = _protect_secret(logged_in)

    created = logged_in.post(
        "/api/bookmarks",
        json={"url": "https://late.example/", "group_id": secret["id"]},
    )
    assert created.status_code == 403
    assert created.get_json()["error"] == "secret_locked_group"

    bookmark = logged_in.post(
        "/api/bookmarks", json={"url": "https://move.example/"}
    ).get_json()["bookmark"]
    moved = logged_in.patch(
        f"/api/bookmarks/{bookmark['id']}", json={"group_id": secret["id"]}
    )
    assert moved.status_code == 403
    assert moved.get_json()["error"] == "secret_locked_group"


def test_locked_secret_not_leaked_via_duplicate_check(logged_in):
    """Regression: a link inside the closed Secret group must not surface
    through the duplicate check (no 409, no title, no group name)."""
    secret = _groups_by_kind(logged_in)["secret"]
    hidden = logged_in.post(
        "/api/bookmarks",
        json={
            "url": "https://dup-secret.example/",
            "title": "Top secret title",
            "group_id": secret["id"],
        },
    ).get_json()["bookmark"]
    _protect_secret(logged_in)

    created = logged_in.post(
        "/api/bookmarks",
        json={"url": "https://dup-secret.example/", "title": "My copy"},
    )
    assert created.status_code == 201
    body = created.get_data(as_text=True)
    assert "Top secret title" not in body
    assert "Secret" not in body

    # Duplicates among visible links still produce a proper 409.
    visible = logged_in.post(
        "/api/bookmarks", json={"url": "https://dup-visible.example/", "title": "Visible"}
    )
    assert visible.status_code == 201
    again = logged_in.post(
        "/api/bookmarks", json={"url": "https://dup-visible.example/"}
    )
    assert again.status_code == 409
    assert again.get_json()["existing"]["id"] == visible.get_json()["bookmark"]["id"]
    assert str(hidden["id"]) not in again.get_data(as_text=True)


def test_secret_unlock_auto_locks_after_ttl(client):
    assert (
        client.post(
            "/api/auth/register", json={"username": "ttl", "password": "secret123"}
        ).status_code
        == 200
    )
    secret = _groups_by_kind(client)["secret"]
    hidden = client.post(
        "/api/bookmarks", json={"url": "https://ttl.example/", "group_id": secret["id"]}
    ).get_json()["bookmark"]
    assert client.patch(f"/api/groups/{secret['id']}", json={"password": "s3cret12"}).status_code == 200
    assert client.post(f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}).status_code == 200
    assert client.get(f"/api/bookmarks/{hidden['id']}").status_code == 200

    # Age the unlock stamp past the TTL: the group must be closed again.
    from bookmarks.db import get_db

    with client.application.app_context():
        db = get_db()
        stale = iso(utcnow() - timedelta(minutes=30))
        db.execute(
            "UPDATE sessions SET secret_unlocked_at = ? WHERE secret_unlocked = 1", (stale,)
        )
        db.commit()

    assert client.get(f"/api/bookmarks/{hidden['id']}").status_code == 404
    assert _groups_by_kind(client)["secret"]["unlocked"] is False
    # A fresh unlock opens the group once more.
    assert client.post(f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}).status_code == 200
    assert client.get(f"/api/bookmarks/{hidden['id']}").status_code == 200


def test_secret_password_change_locks_other_sessions(client):
    assert (
        client.post(
            "/api/auth/register", json={"username": "dual", "password": "secret123"}
        ).status_code
        == 200
    )
    second = client.application.test_client()
    assert (
        second.post(
            "/api/auth/login", json={"username": "dual", "password": "secret123"}
        ).status_code
        == 200
    )
    secret = _groups_by_kind(client)["secret"]
    hidden = client.post(
        "/api/bookmarks",
        json={"url": "https://twosess.example/", "group_id": secret["id"]},
    ).get_json()["bookmark"]
    assert client.patch(f"/api/groups/{secret['id']}", json={"password": "s3cret12"}).status_code == 200
    assert client.post(f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}).status_code == 200
    assert second.post(f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}).status_code == 200
    assert second.get(f"/api/bookmarks/{hidden['id']}").status_code == 200

    # Changing the password re-locks the group in the other browser too.
    changed = client.patch(f"/api/groups/{secret['id']}", json={"password": "n3wpass4"})
    assert changed.status_code == 200
    assert changed.get_json()["group"]["unlocked"] is False
    assert second.get(f"/api/bookmarks/{hidden['id']}").status_code == 404
    assert (
        second.post(
            f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}
        ).get_json()["error"]
        == "wrong_password"
    )
    assert (
        second.post(
            f"/api/groups/{secret['id']}/unlock", json={"password": "n3wpass4"}
        ).status_code
        == 200
    )


def test_trash_bulk_ops_skip_locked_secret(logged_in):
    secret = _groups_by_kind(logged_in)["secret"]
    hidden = logged_in.post(
        "/api/bookmarks",
        json={"url": "https://trash-hidden.example/", "group_id": secret["id"]},
    ).get_json()["bookmark"]
    visible = logged_in.post(
        "/api/bookmarks", json={"url": "https://trash-visible.example/"}
    ).get_json()["bookmark"]
    assert logged_in.delete(f"/api/bookmarks/{hidden['id']}").status_code == 200
    assert logged_in.delete(f"/api/bookmarks/{visible['id']}").status_code == 200
    _protect_secret(logged_in)

    # "Empty trash" must not destroy links the user cannot see right now.
    emptied = logged_in.post("/api/trash/empty").get_json()
    assert emptied["deleted"] == 1
    assert logged_in.get(f"/api/bookmarks/{visible['id']}").status_code == 404

    assert (
        logged_in.post(
            f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}
        ).status_code
        == 200
    )
    trashed = logged_in.get(
        f"/api/bookmarks?view=trash&group_id={secret['id']}"
    ).get_json()["bookmarks"]
    assert [row["id"] for row in trashed] == [hidden["id"]]
    assert logged_in.post("/api/trash/restore-all").get_json()["restored"] == 1


def test_secret_password_change_requires_unlock(logged_in):
    secret = _groups_by_kind(logged_in)["secret"]
    short = logged_in.patch(f"/api/groups/{secret['id']}", json={"password": "1234567"})
    assert short.status_code == 400
    assert short.get_json()["error"] == "secret_password_short"
    assert (
        logged_in.patch(f"/api/groups/{secret['id']}", json={"password": "12345678"})
        .status_code
        == 200
    )

    # Closed again: the password cannot be changed or removed.
    blocked = logged_in.patch(f"/api/groups/{secret['id']}", json={"password": "abcdefgh"})
    assert blocked.status_code == 403
    assert blocked.get_json()["error"] == "secret_locked_group"
    assert (
        logged_in.patch(f"/api/groups/{secret['id']}", json={"password": ""}).status_code
        == 403
    )

    assert (
        logged_in.post(
            f"/api/groups/{secret['id']}/unlock", json={"password": "12345678"}
        ).status_code
        == 200
    )
    changed = logged_in.patch(f"/api/groups/{secret['id']}", json={"password": "abcdefgh"})
    assert changed.status_code == 200
    assert changed.get_json()["group"]["password_set"] is True
    assert changed.get_json()["group"]["unlocked"] is False


# ---------------------------------------------------------------------------
# Pagination & import
# ---------------------------------------------------------------------------


def test_bookmarks_pagination(logged_in):
    for index in range(5):
        created = logged_in.post(
            "/api/bookmarks",
            json={"url": f"https://page.example/{index}", "title": f"Page {index}"},
        )
        assert created.status_code == 201

    first = logged_in.get("/api/bookmarks?limit=2").get_json()
    assert len(first["bookmarks"]) == 2
    assert first["total"] == 5
    assert first["has_more"] is True
    assert (first["limit"], first["offset"]) == (2, 0)

    second = logged_in.get("/api/bookmarks?limit=2&offset=2").get_json()
    assert len(second["bookmarks"]) == 2
    assert second["has_more"] is True
    assert {row["id"] for row in first["bookmarks"]}.isdisjoint(
        {row["id"] for row in second["bookmarks"]}
    )

    last = logged_in.get("/api/bookmarks?limit=2&offset=4").get_json()
    assert len(last["bookmarks"]) == 1
    assert last["has_more"] is False
    assert last["offset"] == 4

    # Out-of-range values are clamped, garbage falls back to defaults.
    assert logged_in.get("/api/bookmarks?limit=10000").get_json()["limit"] == 500
    broken = logged_in.get("/api/bookmarks?limit=abc&offset=-7").get_json()
    assert (broken["limit"], broken["offset"]) == (100, 0)


def test_import_validates_and_respects_locked_secret(logged_in):
    _protect_secret(logged_in)
    payload = {
        "groups": [{"name": "Secret"}, {"name": "Imported", "kind": "custom"}],
        "bookmarks": [
            {
                "url": "https://import.example/good",
                "title": "Good",
                "group": "Imported",
                "created_at": "2001-02-03T04:05:06+00:00",
                "visits": 2,
            },
            {
                "url": "https://import.example/bad-date",
                "title": "Bad date",
                "group": "Secret",
                "created_at": "not-a-date",
                "visits": 10**30,
            },
        ],
    }
    response = logged_in.post(
        "/api/import", json={"format": "json", "content": json.dumps(payload)}
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["imported"] == 2
    assert result["groups_created"] == 1

    groups = logged_in.get("/api/groups").get_json()["groups"]
    assert [row["name"] for row in groups if row["kind"] == "secret"] == ["Secret"]
    imported = next(row for row in groups if row["name"] == "Imported")
    assert imported["count"] == 1

    listed = logged_in.get("/api/bookmarks?limit=500").get_json()["bookmarks"]
    good = next(row for row in listed if row["url"].endswith("/good"))
    assert parse_iso(good["created_at"]).year == 2001
    assert good["visits"] == 2

    # The closed Secret group is not recreated and the link stays visible.
    orphan = next(row for row in listed if row["url"].endswith("/bad-date"))
    assert orphan["group_id"] is None
    assert orphan["visits"] == 1_000_000_000


# A 1x1 PNG that passes validate_image_data_uri.
TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_full_backup_export_contains_profile_settings(logged_in):
    quicklinks = [{"url": "https://quick.example/", "title": "Quick", "icon": TINY_PNG}]
    put = logged_in.put(
        "/api/settings",
        json={"layout": "rows", "fontSize": 18, "lang": "en", "quicklinks": quicklinks},
    )
    assert put.status_code == 200
    account = logged_in.patch(
        "/api/account",
        json={"display_name": "Backup Alice", "avatar_color": "#0ea5e9", "photo": TINY_PNG},
    )
    assert account.status_code == 200

    group = logged_in.post("/api/groups", json={"name": "Work", "icon": "🚀"}).get_json()["group"]
    link = logged_in.post(
        "/api/bookmarks",
        json={
            "url": "https://backup.example/link",
            "title": "Backed up",
            "group_id": group["id"],
            "pinned": True,
            "tags": "work",
        },
    ).get_json()["bookmark"]
    patched = logged_in.patch(f"/api/bookmarks/{link['id']}", json={"icon": TINY_PNG})
    assert patched.status_code == 200
    _protect_secret(logged_in)
    secret = _groups_by_kind(logged_in)["secret"]
    # Exported with the group open: then the password hash rides along too.
    unlocked = logged_in.post(
        f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}
    )
    assert unlocked.status_code == 200
    hidden = logged_in.post(
        "/api/bookmarks", json={"url": "https://backup.example/hidden", "group_id": secret["id"]}
    )
    assert hidden.status_code == 201

    payload = logged_in.get("/api/export").get_json()
    assert payload["export_version"] == 2
    assert payload["user"] == {
        "display_name": "Backup Alice",
        "avatar_color": "#0ea5e9",
        "avatar_photo": TINY_PNG,
    }
    settings = payload["settings"]
    assert settings["layout"] == "rows"
    assert settings["fontSize"] == 18
    assert settings["lang"] == "en"
    assert settings["quicklinks"] == quicklinks
    work = next(row for row in payload["groups"] if row["name"] == "Work")
    assert work["icon"] == "🚀"
    secret_row = next(row for row in payload["groups"] if row["kind"] == "secret")
    assert secret_row["password_hash"]
    exported = {row["url"]: row for row in payload["bookmarks"]}
    assert exported["https://backup.example/link"]["pinned"] is True
    assert exported["https://backup.example/link"]["icon"] == TINY_PNG
    assert exported["https://backup.example/link"]["tags"] == ["work"]
    assert "https://backup.example/hidden" in exported


def test_full_backup_roundtrip_to_second_user(client):
    assert (
        client.post(
            "/api/auth/register", json={"username": "alice", "password": "secret123"}
        ).status_code
        == 200
    )
    quicklinks = [{"url": "https://quick.example/", "title": "Quick", "icon": TINY_PNG}]
    assert (
        client.put(
            "/api/settings",
            json={"layout": "rows", "fontSize": 18, "lang": "en", "quicklinks": quicklinks},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/account",
            json={"display_name": "Alice", "avatar_color": "#0ea5e9", "photo": TINY_PNG},
        ).status_code
        == 200
    )
    group = client.post("/api/groups", json={"name": "Work", "icon": "🚀"}).get_json()["group"]
    link = client.post(
        "/api/bookmarks",
        json={"url": "https://rt.example/link", "group_id": group["id"], "pinned": True},
    ).get_json()["bookmark"]
    assert client.patch(f"/api/bookmarks/{link['id']}", json={"icon": TINY_PNG}).status_code == 200
    secret = _groups_by_kind(client)["secret"]
    assert client.patch(f"/api/groups/{secret['id']}", json={"password": "s3cret12"}).status_code == 200
    # The file must be exported with the group open to carry the hash.
    assert (
        client.post(f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}).status_code
        == 200
    )
    content = client.get("/api/export").get_data(as_text=True)

    # A fresh account restores everything from the file.
    assert (
        client.post(
            "/api/auth/register", json={"username": "bob", "password": "secret123"}
        ).status_code
        == 200
    )
    response = client.post("/api/import", json={"format": "json", "content": content})
    assert response.status_code == 200
    result = response.get_json()
    assert result["imported"] == 1
    assert result["groups_created"] == 1
    assert result["settings_applied"] is True
    assert result["profile_applied"] is True
    assert result["secret_password_restored"] is True

    # The interface is restored: same settings (quick links included).
    settings = client.get("/api/settings").get_json()["settings"]
    assert settings["layout"] == "rows"
    assert settings["fontSize"] == 18
    assert settings["lang"] == "en"
    assert settings["quicklinks"] == quicklinks
    assert result["settings"] == settings

    # And the same profile.
    me = client.get("/api/auth/me").get_json()["user"]
    assert me["display_name"] == "Alice"
    assert me["avatar_color"] == "#0ea5e9"
    assert me["avatar_photo"] == TINY_PNG
    assert result["user"]["display_name"] == "Alice"

    groups = client.get("/api/groups").get_json()["groups"]
    work = next(row for row in groups if row["name"] == "Work")
    assert work["icon"] == "🚀"
    restored_secret = next(row for row in groups if row["kind"] == "secret")
    assert restored_secret["password_set"] is True

    rows = client.get("/api/bookmarks?limit=100").get_json()["bookmarks"]
    imported = next(row for row in rows if row["url"] == "https://rt.example/link")
    assert imported["pinned"] is True
    assert imported["icon"] == TINY_PNG
    assert imported["group_id"] == work["id"]

    # The same Secret password works on the restored account.
    assert (
        client.post(
            f"/api/groups/{restored_secret['id']}/unlock", json={"password": "s3cret12"}
        ).status_code
        == 200
    )


def test_v1_import_keeps_profile_untouched(logged_in):
    account = logged_in.patch(
        "/api/account", json={"display_name": "Keep Me", "avatar_color": "#ef4444"}
    )
    assert account.status_code == 200
    before = logged_in.get("/api/settings").get_json()["settings"]
    payload = {"bookmarks": [{"url": "https://v1.example/", "title": "V1 link"}]}
    response = logged_in.post(
        "/api/import", json={"format": "json", "content": json.dumps(payload)}
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["imported"] == 1
    assert result["settings_applied"] is False
    assert result["profile_applied"] is False
    assert result["secret_password_restored"] is False
    assert "settings" not in result
    assert "user" not in result
    me = logged_in.get("/api/auth/me").get_json()["user"]
    assert me["display_name"] == "Keep Me"
    assert me["avatar_color"] == "#ef4444"
    assert logged_in.get("/api/settings").get_json()["settings"] == before


def test_import_keeps_closed_secret_password(client):
    # Source: protected Secret group, its hash rides along in the file.
    assert (
        client.post(
            "/api/auth/register", json={"username": "src", "password": "secret123"}
        ).status_code
        == 200
    )
    src_secret = _groups_by_kind(client)["secret"]
    assert client.patch(f"/api/groups/{src_secret['id']}", json={"password": "s3cret12"}).status_code == 200
    assert (
        client.post(f"/api/groups/{src_secret['id']}/unlock", json={"password": "s3cret12"}).status_code
        == 200
    )
    content = client.get("/api/export").get_data(as_text=True)

    # Target: a different, already closed Secret group.
    assert (
        client.post(
            "/api/auth/register", json={"username": "dst", "password": "secret123"}
        ).status_code
        == 200
    )
    dst_secret = _groups_by_kind(client)["secret"]
    assert client.patch(f"/api/groups/{dst_secret['id']}", json={"password": "mine1234"}).status_code == 200

    result = client.post("/api/import", json={"format": "json", "content": content}).get_json()
    # A closed target keeps its own password (the same rule as the API).
    assert result["secret_password_restored"] is False
    assert (
        client.post(
            f"/api/groups/{dst_secret['id']}/unlock", json={"password": "mine1234"}
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# Hardening
# ---------------------------------------------------------------------------


def test_ssrf_guard_blocks_private_targets(monkeypatch):
    monkeypatch.delenv("BOOKMARKS_ALLOW_PRIVATE", raising=False)
    monkeypatch.delenv("BOOKMARKS_BLOCK_PRIVATE", raising=False)
    for url in (
        "http://127.0.0.1/",
        "http://10.0.0.5/favicon.ico",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
    ):
        with pytest.raises(FetchError):
            assert_fetchable(url)
    with pytest.raises(FetchError):
        assert_fetchable("file:///C:/Windows/win.ini")
    with pytest.raises(FetchError):
        assert_fetchable("https://user:pass@example.com/")

    # The opt-in restores intranet fetching.
    monkeypatch.setenv("BOOKMARKS_ALLOW_PRIVATE", "1")
    assert_fetchable("http://10.0.0.5/")


def test_http_get_connects_to_pinned_ip(monkeypatch):
    """The socket must go to the IP the SSRF check resolved (DNS-rebinding)."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from bookmarks.util import http_get

    seen_hosts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen_hosts.append(self.headers.get("Host"))
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", "/done")
                self.end_headers()
                return
            body = b"pinned-ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("BOOKMARKS_ALLOW_PRIVATE", "1")
        payload, content_type, final_url = http_get(
            f"http://127.0.0.1:{port}/start", timeout=5.0
        )
        assert payload == b"pinned-ok"
        assert content_type == "text/plain"
        assert final_url.endswith("/done")
        # Every hop carried the correct Host header (with the non-default port).
        assert seen_hosts == [f"127.0.0.1:{port}", f"127.0.0.1:{port}"]
    finally:
        server.shutdown()
        server.server_close()


def test_bookmark_limit(monkeypatch, client):
    monkeypatch.setattr(bookmarks_api, "MAX_BOOKMARKS_PER_USER", 2)
    assert (
        client.post(
            "/api/auth/register", json={"username": "full", "password": "secret123"}
        ).status_code
        == 200
    )
    for index in range(2):
        assert (
            client.post(
                "/api/bookmarks", json={"url": f"https://example.com/page{index}"}
            ).status_code
            == 201
        )
    limited = client.post(
        "/api/bookmarks", json={"url": "https://example.com/page2"}
    )
    assert limited.status_code == 413
    assert limited.get_json()["error"] == "too_many_bookmarks"


def test_tag_limit(monkeypatch, client):
    monkeypatch.setattr(bookmarks_api, "MAX_TAGS_PER_USER", 3)
    assert (
        client.post(
            "/api/auth/register", json={"username": "tags", "password": "secret123"}
        ).status_code
        == 200
    )
    too_many = client.post(
        "/api/bookmarks",
        json={"url": "https://example.com/tags", "tags": "a,b,c,d"},
    )
    assert too_many.status_code == 413
    assert too_many.get_json()["error"] == "too_many_tags"

    # Three tags fit the limit.
    ok = client.post(
        "/api/bookmarks", json={"url": "https://example.com/tags2", "tags": "a,b,c"}
    )
    assert ok.status_code == 201
    # PATCH can grow the tag set too.
    bookmark_id = ok.get_json()["bookmark"]["id"]
    patch = client.patch(
        f"/api/bookmarks/{bookmark_id}", json={"tags": "a,b,c,d"}
    )
    assert patch.status_code == 413
    assert patch.get_json()["error"] == "too_many_tags"
    # Reusing the existing three is fine.
    again = client.patch(
        f"/api/bookmarks/{bookmark_id}", json={"tags": "c,a,b"}
    )
    assert again.status_code == 200


def test_icon_cache_pruning(tmp_path):
    import time

    from bookmarks.db import prune_icon_cache

    icon_dir = tmp_path / "icons"
    icon_dir.mkdir()
    base = time.time() - 100_000
    oldest: list[str] = []
    for index in range(2100):
        name = f"{index:040x}"
        bin_path = icon_dir / (name + ".bin")
        json_path = icon_dir / (name + ".json")
        bin_path.write_bytes(b"x")
        json_path.write_text("{}")
        stamp = base + index
        os.utime(bin_path, (stamp, stamp))
        os.utime(json_path, (stamp, stamp))
        if index < 100:
            oldest.append(name)
    newest = {f"{index:040x}" for index in range(2000, 2100)}

    prune_icon_cache(str(icon_dir), max_files=2000)

    left = {name.name[:-4] for name in icon_dir.iterdir() if name.name.endswith(".bin")}
    assert len(left) == 2000
    assert not (left & set(oldest)), "oldest entries must be dropped"
    assert newest <= left, "newest entries must survive"
    # The meta files of pruned entries go too.
    assert not (icon_dir / (oldest[0] + ".json")).exists()


def test_registration_can_be_closed(monkeypatch, client):
    monkeypatch.setenv("BOOKMARKS_REGISTRATION", "closed")
    closed = client.post(
        "/api/auth/register", json={"username": "late", "password": "secret123"}
    )
    assert closed.status_code == 403
    assert closed.get_json()["error"] == "registration_closed"

    monkeypatch.setenv("BOOKMARKS_REGISTRATION", "open")
    opened = client.post(
        "/api/auth/register", json={"username": "late", "password": "secret123"}
    )
    assert opened.status_code == 200


def _register(client, username, password="secret123"):
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.get_json()["user"]


def _login(client, username, password="secret123"):
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Admin panel & quotas
# ---------------------------------------------------------------------------


def test_first_user_is_admin(client):
    first = _register(client, "boss")
    assert first["is_admin"] is True
    assert first["limits"] == {"bookmarks": 5000, "tags": 100, "groups": 80}

    second = _register(client, "worker")
    assert second["is_admin"] is False
    assert second["limits"] == first["limits"]


def test_startup_grants_admin_to_oldest_user(tmp_path):
    # Databases created before v1.3 have no admin at all: the startup
    # migration promotes the oldest account so the panel is reachable.
    import sqlite3

    from bookmarks import create_app

    database = str(tmp_path / "bookmarks.db")
    application = create_app({"DATABASE": database})
    client = application.test_client()
    _register(client, "boss")
    _register(client, "worker")
    del application, client

    connection = sqlite3.connect(database)
    connection.execute("UPDATE users SET is_admin = 0")
    connection.commit()
    connection.close()

    reborn = create_app({"DATABASE": database})
    probe = reborn.test_client()
    assert (
        probe.post(
            "/api/auth/login", json={"username": "boss", "password": "secret123"}
        ).status_code
        == 200
    )
    assert probe.get("/api/auth/me").get_json()["user"]["is_admin"] is True


def test_admin_summary_counts(client):
    _register(client, "boss")
    _register(client, "worker")  # the client is now the worker: generate usage
    assert (
        client.post(
            "/api/bookmarks", json={"url": "https://a.example/1", "tags": "one"}
        ).status_code
        == 201
    )
    assert (
        client.post("/api/bookmarks", json={"url": "https://a.example/2"}).status_code
        == 201
    )
    # A custom group.
    assert client.post("/api/groups", json={"name": "Work"}).status_code == 201

    _login(client, "boss")
    summary = client.get("/api/admin/summary").get_json()
    assert summary["users_total"] == 2
    assert summary["users_disabled"] == 0
    assert summary["users_active_30d"] == 2
    assert summary["bookmarks"] == 2
    assert summary["trash"] == 0
    assert summary["groups"] == 1  # custom groups only, built-ins excluded
    assert summary["tags"] == 1
    assert summary["db_size_bytes"] > 0
    assert summary["version"]
    assert summary["uptime_seconds"] >= 0


def test_admin_users_list_shows_usage_and_limits(client):
    _register(client, "boss")
    _register(client, "worker")  # the client is now the worker
    assert (
        client.post(
            "/api/bookmarks",
            json={"url": "https://a.example/1", "tags": "one,two"},
        ).status_code
        == 201
    )
    _login(client, "boss")
    listed = client.get("/api/admin/users").get_json()
    assert listed["defaults"] == {"bookmarks": 5000, "tags": 100, "groups": 80}
    rows = {row["username"]: row for row in listed["users"]}
    assert set(rows) == {"boss", "worker"}
    assert rows["boss"]["is_admin"] is True
    assert rows["worker"]["is_admin"] is False
    assert rows["worker"]["bookmarks"] == 1
    assert rows["worker"]["tags"] == 2
    assert rows["worker"]["sessions"] == 1
    assert rows["worker"]["limits"] == {"bookmarks": 5000, "tags": 100, "groups": 80}
    assert rows["worker"]["custom_limits"] == {
        "bookmarks": None,
        "tags": None,
        "groups": None,
    }


def test_non_admin_cannot_open_admin_panel(client):
    _register(client, "boss")  # first user, admin
    client.post("/api/auth/logout", json={})
    second = client.post(
        "/api/auth/register", json={"username": "worker", "password": "secret123"}
    )
    assert second.status_code == 200
    denied = client.get("/api/admin/users")
    assert denied.status_code == 403
    assert denied.get_json()["error"] == "not_admin"
    denied_patch = client.patch("/api/admin/users/2", json={"disabled": 1})
    assert denied_patch.status_code == 403

    # Anonymous requests still see the regular 401.
    fresh = client.application.test_client()
    assert fresh.get("/api/admin/summary").status_code == 401


def test_admin_sets_bookmark_limit(client):
    _register(client, "boss")
    worker = _register(client, "worker")
    _login(client, "boss")
    worker_id = worker["id"]

    denied = client.patch(
        f"/api/admin/users/{worker_id}", json={"max_bookmarks": 2}
    )
    assert denied.status_code == 200
    assert denied.get_json()["user"]["limits"]["bookmarks"] == 2
    assert denied.get_json()["user"]["custom_limits"]["bookmarks"] == 2

    # The worker runs out of the tightened quota.
    client.post("/api/auth/logout", json={})
    _login(client, "worker")
    for index in range(2):
        assert (
            client.post(
                "/api/bookmarks", json={"url": f"https://q.example/{index}"}
            ).status_code
            == 201
        )
    over = client.post("/api/bookmarks", json={"url": "https://q.example/over"})
    assert over.status_code == 413
    assert over.get_json()["error"] == "too_many_bookmarks"
    assert over.get_json()["limit"] == 2

    # Back to the global default (NULL override): the worker may save again.
    client.post("/api/auth/logout", json={})
    _login(client, "boss")
    reset = client.patch(
        f"/api/admin/users/{worker_id}", json={"max_bookmarks": None}
    )
    assert reset.status_code == 200
    assert reset.get_json()["user"]["limits"]["bookmarks"] == 5000
    client.post("/api/auth/logout", json={})
    _login(client, "worker")
    assert (
        client.post("/api/bookmarks", json={"url": "https://q.example/over"}).status_code
        == 201
    )

    # Invalid values are rejected without touching the stored override.
    client.post("/api/auth/logout", json={})
    _login(client, "boss")
    for bad in ("x", 0, -5, 100001):
        rejected = client.patch(
            f"/api/admin/users/{worker_id}", json={"max_bookmarks": bad}
        )
        assert rejected.status_code == 400
        assert rejected.get_json()["error"] == "invalid_limit"


def test_admin_sets_tag_and_group_limits(client):
    _register(client, "boss")
    worker = _register(client, "worker")
    _login(client, "boss")
    worker_id = worker["id"]

    assert (
        client.patch(f"/api/admin/users/{worker_id}", json={"max_tags": 2}).status_code
        == 200
    )

    # The worker hits the tightened limits.
    client.post("/api/auth/logout", json={})
    _login(client, "worker")
    assert (
        client.post(
            "/api/bookmarks", json={"url": "https://q.example/t", "tags": "a,b,c"}
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/bookmarks", json={"url": "https://q.example/t", "tags": "a,b"}
        ).status_code
        == 201
    )

    # Groups: the account already owns the built-in Favorites + Secret.
    client.post("/api/auth/logout", json={})
    _login(client, "boss")
    assert (
        client.patch(f"/api/admin/users/{worker_id}", json={"max_groups": 3}).status_code
        == 200
    )
    client.post("/api/auth/logout", json={})
    _login(client, "worker")
    first = client.post("/api/groups", json={"name": "First"})
    assert first.status_code == 201
    second = client.post("/api/groups", json={"name": "Second"})
    assert second.status_code == 413
    assert second.get_json()["error"] == "too_many_groups"
    assert second.get_json()["limit"] == 3


def test_admin_cannot_demote_or_disable_self(client):
    _register(client, "boss")  # first user -> admin
    boss_id = client.get("/api/auth/me").get_json()["user"]["id"]
    helper = _register(client, "helper")
    _login(client, "boss")  # registration switched the session to "helper"

    # The boss is the only admin: demoting themselves would leave the
    # panel unreachable without a CLI.
    demote = client.patch(f"/api/admin/users/{boss_id}", json={"is_admin": False})
    assert demote.status_code == 400
    assert demote.get_json()["error"] == "last_admin"

    # Changing their own quotas is fine, though.
    own = client.patch(f"/api/admin/users/{boss_id}", json={"max_bookmarks": 123})
    assert own.status_code == 200
    assert own.get_json()["user"]["limits"]["bookmarks"] == 123

    # With a second admin around, self-blocking is still refused (the
    # other admin can unlock the account) ...
    assert (
        client.patch(f"/api/admin/users/{helper['id']}", json={"is_admin": True}).status_code
        == 200
    )
    lock = client.patch(f"/api/admin/users/{boss_id}", json={"disabled": True})
    assert lock.status_code == 400
    assert lock.get_json()["error"] == "cannot_change_self"

    # ... but self-demotion is allowed: the helper keeps the panel alive.
    demote2 = client.patch(f"/api/admin/users/{boss_id}", json={"is_admin": False})
    assert demote2.status_code == 200
    assert demote2.get_json()["user"]["is_admin"] is False


def test_last_admin_cannot_be_demoted_or_blocked(client):
    boss = _register(client, "boss")  # first user, already an admin
    worker = _register(client, "worker")
    _login(client, "boss")

    # Promote the worker, then demote the boss: allowed while two admins exist.
    assert (
        client.patch(f"/api/admin/users/{worker['id']}", json={"is_admin": True}).status_code
        == 200
    )
    assert (
        client.patch(f"/api/admin/users/{boss['id']}", json={"is_admin": False}).status_code
        == 200
    )

    # The worker is now the only admin: demoting or blocking them is refused,
    # otherwise the panel would become unreachable without a CLI.
    client.post("/api/auth/logout", json={})
    assert (
        client.post(
            "/api/auth/login", json={"username": "worker", "password": "secret123"}
        ).status_code
        == 200
    )
    demote = client.patch(f"/api/admin/users/{worker['id']}", json={"is_admin": False})
    assert demote.status_code == 400
    assert demote.get_json()["error"] == "last_admin"
    block = client.patch(f"/api/admin/users/{worker['id']}", json={"disabled": True})
    assert block.status_code == 400
    assert block.get_json()["error"] == "last_admin"


def test_admin_reset_password_invalidates_sessions(client):
    _register(client, "boss")
    worker = _register(client, "worker")
    _login(client, "boss")
    worker_id = worker["id"]

    assert (
        client.post(
            f"/api/admin/users/{worker_id}/password", json={"password": "freshpass1"}
        ).status_code
        == 200
    )
    # The caller (boss) keeps their own session.
    assert client.get("/api/auth/me").status_code == 200

    fresh = client.application.test_client()
    # The worker's previous session is gone — a re-login with the old
    # password fails, with the new one succeeds.
    old = fresh.post(
        "/api/auth/login", json={"username": "worker", "password": "secret123"}
    )
    assert old.status_code == 401
    new = fresh.post(
        "/api/auth/login", json={"username": "worker", "password": "freshpass1"}
    )
    assert new.status_code == 200

    # Weak passwords are refused.
    weak = client.post(
        f"/api/admin/users/{worker_id}/password", json={"password": "short"}
    )
    assert weak.status_code == 400
    assert weak.get_json()["error"] == "weak_password"


def test_admin_patch_requires_known_fields(client):
    _register(client, "boss")
    boss_id = client.get("/api/auth/me").get_json()["user"]["id"]
    empty = client.patch(f"/api/admin/users/{boss_id}", json={})
    assert empty.status_code == 400
    assert empty.get_json()["error"] == "nothing_to_update"
    missing = client.patch("/api/admin/users/999", json={"disabled": True})
    assert missing.status_code == 404
    assert missing.get_json()["error"] == "user_not_found"


def test_manage_make_admin(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    from bookmarks import create_app

    root = Path(__file__).resolve().parents[1]
    data_dir = tmp_path / "data"
    application = create_app({"DATABASE": str(data_dir / "bookmarks.db")})
    with application.app_context():
        pass
    client = application.test_client()
    assert (
        client.post(
            "/api/auth/register", json={"username": "plain", "password": "secret123"}
        ).status_code
        == 200
    )
    # A second account: not an admin yet, the CLI must promote it.
    assert (
        client.post(
            "/api/auth/register", json={"username": "other", "password": "secret123"}
        ).status_code
        == 200
    )

    env = dict(os.environ, BOOKMARKS_DATA=str(data_dir))
    result = subprocess.run(
        [sys.executable, str(root / "manage.py"), "make-admin", "other"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # The panel is reachable with the fresh session of that account.
    fresh = client.application.test_client()
    assert (
        fresh.post(
            "/api/auth/login", json={"username": "other", "password": "secret123"}
        ).status_code
        == 200
    )
    assert fresh.get("/api/admin/users").status_code == 200
    assert fresh.get("/api/auth/me").get_json()["user"]["is_admin"] is True


def test_unlock_is_rate_limited(logged_in):
    # Kept last: the limiter keeps module-level state per user/group.
    secret = _protect_secret(logged_in)
    uid = logged_in.get("/api/auth/me").get_json()["user"]["id"]
    key = f"unlock|{uid}|{secret['id']}"
    ratelimit.reset(key)

    for _ in range(ratelimit.LIMIT):
        wrong = logged_in.post(
            f"/api/groups/{secret['id']}/unlock", json={"password": "nope"}
        )
        assert wrong.status_code == 400

    blocked = logged_in.post(
        f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}
    )
    assert blocked.status_code == 429
    assert blocked.get_json()["error"] == "rate_limited"

    # A successful unlock after the window is allowed and clears the state.
    ratelimit.reset(key)
    assert (
        logged_in.post(
            f"/api/groups/{secret['id']}/unlock", json={"password": "s3cret12"}
        ).status_code
        == 200
    )
