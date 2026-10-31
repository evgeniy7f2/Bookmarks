"""API tests: auth, groups, bookmarks, settings, export.

Run from the project root:  python -m pytest tests/ -v
"""

from __future__ import annotations

import re

from bookmarks.util import parse_iso

# ---------------------------------------------------------------------------
# Health & auth
# ---------------------------------------------------------------------------


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


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

    ok = logged_in.patch(f"/api/groups/{secret_id}", json={"password": "s3cret"})
    assert ok.status_code == 200
    assert ok.get_json()["group"]["password_set"] is True
    # After setting a password the group is locked again.
    assert ok.get_json()["group"]["unlocked"] is False

    # A link added to the secret group is invisible on the home feed.
    created = logged_in.post(
        "/api/bookmarks",
        json={"url": "https://secret.example/", "title": "Hidden", "group_id": secret_id},
    )
    assert created.status_code == 201
    link_id = created.get_json()["bookmark"]["id"]
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
        f"/api/groups/{secret_id}/unlock", json={"password": "s3cret"}
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
    logged_in.post(f"/api/groups/{secret_id}/unlock", json={"password": "s3cret"})
    opened = logged_in.patch(f"/api/groups/{secret_id}", json={"password": ""})
    assert opened.status_code == 200
    assert opened.get_json()["group"]["password_set"] is False
    assert opened.get_json()["group"]["unlocked"] is True
    links = logged_in.get(f"/api/bookmarks?group_id={secret_id}").get_json()["bookmarks"]
    assert [row["id"] for row in links] == [link_id]
    no_password = logged_in.post(
        f"/api/groups/{secret_id}/unlock", json={"password": "s3cret"}
    )
    assert no_password.status_code == 400
    assert no_password.get_json()["error"] == "secret_no_password"


def test_home_still_shows_ungrouped_and_custom(logged_in):
    # Regression: excluding the secret group from general feeds must not
    # drop links whose group_id is NULL (ungrouped) or a custom group.
    groups = logged_in.get("/api/groups").get_json()["groups"]
    secret = next(row for row in groups if row["kind"] == "secret")
    assert logged_in.patch(f"/api/groups/{secret['id']}", json={"password": "s3cret"}).status_code == 200

    custom = logged_in.post("/api/groups", json={"name": "Work"}).get_json()["group"]

    secret_link = logged_in.post(
        "/api/bookmarks", json={"url": "https://s.example/", "title": "S", "group_id": secret["id"]}
    ).get_json()["bookmark"]
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
