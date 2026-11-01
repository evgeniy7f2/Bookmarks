"""JSON API for groups, bookmarks, tags, metadata and data transfer."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import defaultdict

from flask import Blueprint, current_app, g, jsonify, request, send_file

from . import ratelimit
from .db import get_db
from .settings import load_settings, normalize_settings
from .util import (
    APP_NAME,
    APP_VERSION,
    LIMIT_BOUNDS,
    MAX_BOOKMARKS_PER_USER,
    MAX_GROUPS_PER_USER,
    MAX_TAGS_PER_USER,
    SECRET_UNLOCK_TTL,
    clean_text,
    fetch_favicon,
    fetch_page_metadata,
    guess_title,
    hash_password,
    hash_token,
    iso,
    is_valid_color,
    like_pattern,
    normalize_url,
    parse_iso,
    parse_tags,
    utcnow,
    validate_image_data_uri,
    verify_password,
)

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.before_request
def require_login():
    if g.get("user") is None:
        return jsonify({"error": "unauthorized"}), 401


def _db():
    return get_db()


def _uid() -> int:
    return int(g.user["id"])


def _error(code: str, status: int = 400, **extra):
    payload = {"error": code}
    payload.update(extra)
    return jsonify(payload), status


def _json() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _tags_for(db, ids: list[int]) -> dict[int, list[str]]:
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = db.execute(
        f"""
        SELECT bt.bookmark_id, t.name
        FROM bookmark_tags bt JOIN tags t ON t.id = bt.tag_id
        WHERE bt.bookmark_id IN ({placeholders})
        ORDER BY t.name COLLATE NOCASE
        """,
        ids,
    ).fetchall()
    result: dict[int, list[str]] = defaultdict(list)
    for row in rows:
        result[row["bookmark_id"]].append(row["name"])
    return result


def _bookmark_dict(row, tags: list[str] | None = None) -> dict:
    is_favorite_copy = row["group_kind"] == "favorites"
    has_copy = bool(row["has_fav_copy"]) if "has_fav_copy" in row.keys() else False
    return {
        "id": row["id"],
        "url": row["url"],
        "title": row["title"],
        "description": row["description"],
        "group_id": row["group_id"],
        "group_name": row["group_name"],
        "group_icon": row["group_icon"],
        "group_kind": row["group_kind"],
        "pinned": bool(row["pinned"]),
        "visits": row["visits"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_visit_at": row["last_visit_at"],
        "deleted_at": row["deleted_at"],
        "origin_id": row["origin_id"],
        "icon": row["icon"],
        "tags": tags or [],
        "favorited": bool(is_favorite_copy or has_copy),
        "is_favorite_copy": bool(is_favorite_copy),
    }


BOOKMARK_SELECT = """
SELECT b.*, g.name AS group_name, g.icon AS group_icon, g.kind AS group_kind,
       EXISTS(
           SELECT 1 FROM bookmarks f JOIN groups fg ON fg.id = f.group_id
           WHERE f.origin_id = b.id AND fg.kind = 'favorites' AND f.deleted_at IS NULL
       ) AS has_fav_copy
FROM bookmarks b
LEFT JOIN groups g ON g.id = b.group_id
"""


def secret_locked(db, user_id: int) -> bool:
    """Whether the Secret group is password-protected and closed for this session."""
    return not _secret_unlocked(db, user_id)


def _fetch_bookmark(db, user_id: int, bookmark_id: int, *, allow_locked: bool = False):
    row = db.execute(
        BOOKMARK_SELECT + " WHERE b.id = ? AND b.user_id = ?", (bookmark_id, user_id)
    ).fetchone()
    if row is None or allow_locked:
        return row
    if row["group_kind"] == "secret" and secret_locked(db, user_id):
        # Locked Secret links must be indistinguishable from missing ones.
        return None
    return row


def _bookmark_payload(db, row) -> dict:
    tags = _tags_for(db, [row["id"]]) if row else {}
    return _bookmark_dict(row, tags.get(row["id"], []))


def _get_group(db, user_id: int, group_id):
    if group_id in (None, "", 0, "0"):
        return None
    try:
        gid = int(group_id)
    except (TypeError, ValueError):
        return None
    return db.execute("SELECT * FROM groups WHERE id = ? AND user_id = ?", (gid, user_id)).fetchone()


def _secret_unlocked(db, user_id: int) -> bool:
    """Whether the Secret group is open for this browser session.

    A group without a password is always open. Otherwise the flag lives on
    the session row of the current cookie (survives reloads, per browser)
    and carries a stamp: after SECRET_UNLOCK_TTL without activity the
    group is auto-locked again.
    """
    row = db.execute(
        "SELECT * FROM groups WHERE user_id = ? AND kind = 'secret' ORDER BY id LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None or not row["password_hash"]:
        return True
    token = request.cookies.get(current_app.config["SESSION_COOKIE"])
    if not token:
        return False
    flag = db.execute(
        "SELECT secret_unlocked, secret_unlocked_at"
        " FROM sessions WHERE token_hash = ? AND user_id = ?",
        (hash_token(token), user_id),
    ).fetchone()
    if not flag or not flag["secret_unlocked"]:
        return False
    if flag["secret_unlocked_at"]:
        unlocked_at = parse_iso(flag["secret_unlocked_at"])
        if unlocked_at is not None and utcnow() - unlocked_at > SECRET_UNLOCK_TTL:
            db.execute(
                "UPDATE sessions SET secret_unlocked = 0, secret_unlocked_at = NULL"
                " WHERE token_hash = ? AND user_id = ?",
                (hash_token(token), user_id),
            )
            return False
    else:
        # Row from before the TTL column existed: treat as fresh.
        db.execute(
            "UPDATE sessions SET secret_unlocked_at = ?"
            " WHERE token_hash = ? AND user_id = ?",
            (iso(), hash_token(token), user_id),
        )
    return True


def _set_secret_unlocked(db, user_id: int, value: int) -> None:
    token = request.cookies.get(current_app.config["SESSION_COOKIE"])
    if value:
        stamp = iso()
        if token:
            db.execute(
                "UPDATE sessions SET secret_unlocked = 1, secret_unlocked_at = ?"
                " WHERE token_hash = ? AND user_id = ?",
                (stamp, hash_token(token), user_id),
            )
        else:
            db.execute(
                "UPDATE sessions SET secret_unlocked = 1, secret_unlocked_at = ?"
                " WHERE user_id = ?",
                (stamp, user_id),
            )
    else:
        if token:
            db.execute(
                "UPDATE sessions SET secret_unlocked = 0, secret_unlocked_at = NULL"
                " WHERE token_hash = ? AND user_id = ?",
                (hash_token(token), user_id),
            )
        else:
            db.execute(
                "UPDATE sessions SET secret_unlocked = 0, secret_unlocked_at = NULL"
                " WHERE user_id = ?",
                (user_id,),
            )


def _group_payload(db, group, user_id: int, count: int | None = None) -> dict:
    unlocked = _secret_unlocked(db, user_id) if group["kind"] == "secret" else True
    if count is None:
        count = db.execute(
            "SELECT COUNT(*) c FROM bookmarks WHERE group_id = ? AND deleted_at IS NULL",
            (group["id"],),
        ).fetchone()["c"]
    return {
        "id": group["id"],
        "name": group["name"],
        "icon": group["icon"],
        "kind": group["kind"],
        "position": group["position"],
        # A closed Secret group does not advertise how many links it holds.
        "count": 0 if group["kind"] == "secret" and not unlocked else count,
        "password_set": bool(group["password_hash"]),
        "unlocked": unlocked,
    }


def _favorites_group(db, user_id: int):
    row = db.execute(
        "SELECT * FROM groups WHERE user_id = ? AND kind = 'favorites' ORDER BY id LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None:
        cursor = db.execute(
            "INSERT INTO groups(user_id, name, icon, kind, position, created_at)"
            " VALUES (?, 'Favorites', '🔥', 'favorites', 0, ?)",
            (user_id, iso()),
        )
        db.commit()
        row = db.execute("SELECT * FROM groups WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row


def _set_tags(db, user_id: int, bookmark_id: int, tags: list[str]) -> None:
    db.execute("DELETE FROM bookmark_tags WHERE bookmark_id = ?", (bookmark_id,))
    for name in tags:
        db.execute(
            "INSERT INTO tags(user_id, name) VALUES (?, ?) ON CONFLICT(user_id, name) DO NOTHING",
            (user_id, name),
        )
        tag = db.execute(
            "SELECT id FROM tags WHERE user_id = ? AND name = ? COLLATE NOCASE", (user_id, name)
        ).fetchone()
        if tag:
            db.execute(
                "INSERT OR IGNORE INTO bookmark_tags(bookmark_id, tag_id) VALUES (?, ?)",
                (bookmark_id, tag["id"]),
            )


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


@bp.get("/groups")
def list_groups():
    db = _db()
    uid = _uid()
    rows = db.execute(
        """
        SELECT g.*, COUNT(b.id) AS count
        FROM groups g
        LEFT JOIN bookmarks b
            ON b.group_id = g.id AND b.user_id = g.user_id AND b.deleted_at IS NULL
        WHERE g.user_id = ?
        GROUP BY g.id
        ORDER BY
            CASE g.kind WHEN 'favorites' THEN 0 WHEN 'secret' THEN 1 ELSE 2 END,
            g.position, g.id
        """,
        (uid,),
    ).fetchall()
    return jsonify(
        {"groups": [_group_payload(db, row, uid, row["count"]) for row in rows]}
    )


RESERVED_GROUP_NAMES = {"favorites", "secret"}


def _group_name_clash(db, user_id: int, name: str):
    """Return an error tuple if *name* is reserved or already taken."""
    if name.casefold() in RESERVED_GROUP_NAMES:
        return _error("group_name_reserved", 409)
    clash = db.execute(
        "SELECT 1 FROM groups WHERE user_id = ? AND name = ? COLLATE NOCASE LIMIT 1",
        (user_id, name),
    ).fetchone()
    if clash:
        return _error("group_name_taken", 409)
    return None


@bp.post("/groups")
def create_group():
    data = _json()
    name = clean_text(data.get("name"), 40)
    icon = clean_text(data.get("icon"), 8) or "📁"
    if not name:
        return _error("group_name_required")
    db = _db()
    uid = _uid()
    group_limit = _user_limits(db, uid)["groups"]
    total = db.execute("SELECT COUNT(*) c FROM groups WHERE user_id = ?", (uid,)).fetchone()["c"]
    if total >= group_limit:
        return _error("too_many_groups", 413, limit=group_limit)
    problem = _group_name_clash(db, uid, name)
    if problem:
        return problem
    position = db.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 p FROM groups WHERE user_id = ?", (uid,)
    ).fetchone()["p"]
    try:
        cursor = db.execute(
            "INSERT INTO groups(user_id, name, icon, kind, position, created_at)"
            " VALUES (?, ?, ?, 'custom', ?, ?)",
            (uid, name, icon, position, iso()),
        )
    except sqlite3.IntegrityError:
        return _error("group_name_taken", 409)
    db.commit()
    row = db.execute(
        "SELECT * FROM groups WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return (
        jsonify({"group": _group_payload(db, row, uid)}),
        201,
    )


def _update_secret_group(db, group, data) -> tuple:
    """The Secret group keeps its name and icon; only the password changes.

    Non-empty password (min 8 chars) sets a new one and locks the group
    again; an empty one removes the password (the group becomes open).
    The group must be unlocked first, otherwise any session could silently
    reset or remove the protection.
    """
    uid = _uid()
    if "password" not in data:
        return _error("secret_locked")
    if group["password_hash"] and secret_locked(db, uid):
        return _error("secret_locked_group", 403)
    password = data.get("password")
    password = password.strip() if isinstance(password, str) else ""
    if password:
        if len(password) < 8:
            return _error("secret_password_short")
        if len(password) > 200:
            return _error("password_too_long")
        db.execute(
            "UPDATE groups SET password_hash = ? WHERE id = ? AND user_id = ?",
            (hash_password(password), group["id"], uid),
        )
        # The old password stops working everywhere: re-lock the group in
        # every session, not just the one that made the change.
        db.execute(
            "UPDATE sessions SET secret_unlocked = 0, secret_unlocked_at = NULL"
            " WHERE user_id = ?",
            (uid,),
        )
    else:
        db.execute(
            "UPDATE groups SET password_hash = NULL WHERE id = ? AND user_id = ?",
            (group["id"], uid),
        )
        _set_secret_unlocked(db, uid, 1)
    ratelimit.reset(f"unlock|{uid}|{group['id']}")
    db.commit()
    group = _get_group(db, uid, group["id"])
    return jsonify({"group": _group_payload(db, group, uid)})


@bp.patch("/groups/<int:group_id>")
def update_group(group_id: int):
    db = _db()
    group = _get_group(db, _uid(), group_id)
    if group is None:
        return _error("not_found", 404)
    if group["kind"] == "favorites":
        return _error("favorites_locked")
    if group["kind"] == "secret":
        return _update_secret_group(db, group, _json())
    data = _json()
    name = clean_text(data.get("name"), 40) if "name" in data else group["name"]
    icon = clean_text(data.get("icon"), 8) if "icon" in data else group["icon"]
    if not name:
        return _error("group_name_required")
    if name != group["name"]:
        problem = _group_name_clash(db, _uid(), name)
        if problem:
            return problem
    try:
        db.execute(
            "UPDATE groups SET name = ?, icon = ? WHERE id = ?", (name, icon or "📁", group_id)
        )
    except sqlite3.IntegrityError:
        return _error("group_name_taken", 409)
    db.commit()
    group = _get_group(db, _uid(), group_id)
    return jsonify({"group": _group_payload(db, group, _uid())})


@bp.delete("/groups/<int:group_id>")
def delete_group(group_id: int):
    db = _db()
    uid = _uid()
    group = _get_group(db, uid, group_id)
    if group is None:
        return _error("not_found", 404)
    if group["kind"] == "favorites":
        return _error("favorites_locked")
    if group["kind"] == "secret":
        return _error("secret_locked")
    moved = db.execute(
        "SELECT COUNT(*) c FROM bookmarks WHERE group_id = ? AND deleted_at IS NULL", (group_id,)
    ).fetchone()["c"]
    db.execute(
        "UPDATE bookmarks SET group_id = NULL, deleted_at = COALESCE(deleted_at, ?)"
        " WHERE group_id = ? AND user_id = ?",
        (iso(), group_id, uid),
    )
    db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    db.commit()
    return jsonify({"ok": True, "moved_to_trash": moved})


@bp.post("/groups/<int:group_id>/unlock")
def unlock_group(group_id: int):
    db = _db()
    uid = _uid()
    group = _get_group(db, uid, group_id)
    if group is None:
        return _error("not_found", 404)
    if group["kind"] != "secret":
        return _error("not_secret")
    if not group["password_hash"]:
        return _error("secret_no_password")
    key = f"unlock|{uid}|{group_id}"
    if ratelimit.is_limited(key):
        return _error("rate_limited", 429)
    password = _json().get("password")
    if not isinstance(password, str) or not password:
        return _error("password_required")
    if not verify_password(password, group["password_hash"]):
        ratelimit.remember(key)
        return _error("wrong_password")
    ratelimit.reset(key)
    _set_secret_unlocked(db, uid, 1)
    db.commit()
    return jsonify({"ok": True, "unlocked": True})


@bp.post("/groups/<int:group_id>/lock")
def lock_group(group_id: int):
    db = _db()
    uid = _uid()
    group = _get_group(db, uid, group_id)
    if group is None:
        return _error("not_found", 404)
    if group["kind"] != "secret":
        return _error("not_secret")
    _set_secret_unlocked(db, uid, 0)
    db.commit()
    return jsonify({"ok": True, "unlocked": False})


@bp.post("/groups/reorder")
def reorder_groups():
    data = _json()
    ids = data.get("ids")
    if not isinstance(ids, list):
        return _error("invalid_payload")
    db = _db()
    uid = _uid()
    valid = {
        row["id"]
        for row in db.execute(
            "SELECT id FROM groups WHERE user_id = ? AND kind = 'custom'", (uid,)
        ).fetchall()
    }
    position = 1
    for raw_id in ids:
        try:
            group_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if group_id in valid:
            db.execute(
                "UPDATE groups SET position = ? WHERE id = ? AND user_id = ?",
                (position, group_id, uid),
            )
            position += 1
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
MAX_IMPORT_ITEMS = 5000
# Storage guards: a single account cannot bloat the shared database, and the
# tag dictionary cannot grow without bound. The defaults live in util.py
# (MAX_*); admins can tighten or raise them per user, stored in users.max_*.


def _user_limits(db, user_id: int) -> dict[str, int]:
    """Effective quotas for an account (per-user override or global default)."""
    row = db.execute(
        "SELECT max_bookmarks, max_tags, max_groups FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return {
        "bookmarks": int(row["max_bookmarks"] or MAX_BOOKMARKS_PER_USER),
        "tags": int(row["max_tags"] or MAX_TAGS_PER_USER),
        "groups": int(row["max_groups"] or MAX_GROUPS_PER_USER),
    }


def _tag_usage(db, user_id: int, tags: list[str]) -> tuple[int, int]:
    """Return (existing_tags, new_tags) for *tags*, case-insensitive."""
    existing = {
        row["name"].casefold()
        for row in db.execute("SELECT name FROM tags WHERE user_id = ?", (user_id,))
    }
    new = {name.casefold() for name in tags} - existing
    return len(existing), len(new)


def _page_args() -> tuple[int, int]:
    """Return a sane (limit, offset) pair for list endpoints."""
    try:
        limit = int(request.args.get("limit", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        limit = DEFAULT_PAGE_SIZE
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    return max(1, min(MAX_PAGE_SIZE, limit)), max(0, offset)


@bp.get("/bookmarks")
def list_bookmarks():
    db = _db()
    uid = _uid()
    trash = request.args.get("view") == "trash"
    favorites = request.args.get("favorites") in ("1", "true", "yes")
    group_id = request.args.get("group_id")
    tag = clean_text(request.args.get("tag"), 64)
    query = clean_text(request.args.get("q"), 160)
    sort = request.args.get("sort") or ("deleted" if trash else "created")
    direction = request.args.get("sort_dir") or "desc"
    limit, offset = _page_args()

    where = " WHERE b.user_id = ?"
    params: list[object] = [uid]
    where += " AND b.deleted_at IS NOT NULL" if trash else " AND b.deleted_at IS NULL"
    empty_page = {
        "bookmarks": [],
        "total": 0,
        "has_more": False,
        "limit": limit,
        "offset": offset,
    }

    secret_ids = [
        row["id"]
        for row in db.execute(
            "SELECT id FROM groups WHERE user_id = ? AND kind = 'secret'", (uid,)
        ).fetchall()
    ]

    if favorites:
        where += " AND g.kind = 'favorites'"
    elif group_id not in (None, "", "0"):
        group = _get_group(db, uid, group_id)
        if group is None:
            return _error("not_found", 404)
        if group["kind"] == "secret" and not _secret_unlocked(db, uid):
            # Locked: the links stay invisible to this session.
            return jsonify(empty_page)
        where += " AND b.group_id = ?"
        params.append(group["id"])
    elif secret_ids:
        # General feeds (home, search, tags). Secret-group links never show
        # up on home (even unlocked), and they stay hidden in search/tags
        # while the group is locked.
        hide_secret = (not tag and not query) or not _secret_unlocked(db, uid)
        if hide_secret:
            # group_id is NULL for ungrouped links, and `NULL NOT IN (...)`
            # is not TRUE — so keep the NULLs explicitly.
            placeholders = ", ".join("?" * len(secret_ids))
            where += f" AND (b.group_id IS NULL OR b.group_id NOT IN ({placeholders}))"
            params.extend(secret_ids)

    if tag:
        where += (
            " AND EXISTS (SELECT 1 FROM bookmark_tags bt JOIN tags t ON t.id = bt.tag_id"
            " WHERE bt.bookmark_id = b.id AND t.name = ? COLLATE NOCASE)"
        )
        params.append(tag)

    if query:
        tokens = [token for token in query.split() if token][:6]
        for token in tokens:
            pattern = like_pattern(token)
            where += (
                " AND (b.title LIKE ? ESCAPE '\\' OR b.url LIKE ? ESCAPE '\\'"
                " OR b.description LIKE ? ESCAPE '\\'"
                " OR EXISTS (SELECT 1 FROM bookmark_tags bt JOIN tags t ON t.id = bt.tag_id"
                " WHERE bt.bookmark_id = b.id AND t.name LIKE ? ESCAPE '\\'))"
            )
            params.extend([pattern, pattern, pattern, pattern])

    order_map = {
        "title": "b.title COLLATE NOCASE",
        "created": "b.created_at",
        "updated": "b.updated_at",
        "visits": "b.visits",
        "deleted": "b.deleted_at",
    }
    order = order_map.get(sort, "b.created_at")
    if trash and sort == "created":
        order = "b.deleted_at"
    direction_sql = "ASC" if direction == "asc" else "DESC"
    pinned_sql = "" if trash else "b.pinned DESC, "

    base = BOOKMARK_SELECT + where
    total = int(
        db.execute(f"SELECT COUNT(*) AS c FROM ({base})", params).fetchone()["c"]
    )
    rows = db.execute(
        f"{base} ORDER BY {pinned_sql}{order} {direction_sql}, b.id {direction_sql}"
        " LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    tags = _tags_for(db, [row["id"] for row in rows])
    return jsonify(
        {
            "bookmarks": [_bookmark_dict(row, tags.get(row["id"], [])) for row in rows],
            "total": total,
            "has_more": offset + len(rows) < total,
            "limit": limit,
            "offset": offset,
        }
    )


@bp.post("/bookmarks")
def create_bookmark():
    db = _db()
    uid = _uid()
    data = _json()
    try:
        url = normalize_url(str(data.get("url") or ""))
    except ValueError as exc:
        return _error("invalid_url", 400, message=str(exc))
    title = clean_text(data.get("title"), 300) or guess_title(url)
    description = clean_text(data.get("description"), 2000, multiline=True)
    tags = parse_tags(data.get("tags"))
    group = _get_group(db, uid, data.get("group_id"))
    if data.get("group_id") not in (None, "", 0, "0") and group is None:
        return _error("group_not_found", 404)
    if group is not None and group["kind"] == "secret" and secret_locked(db, uid):
        # A closed Secret group cannot receive links: they would vanish.
        return _error("secret_locked_group", 403)
    limits = _user_limits(db, uid)
    used = db.execute(
        "SELECT COUNT(*) c FROM bookmarks WHERE user_id = ? AND deleted_at IS NULL", (uid,)
    ).fetchone()["c"]
    if used >= limits["bookmarks"]:
        return _error("too_many_bookmarks", 413, limit=limits["bookmarks"])
    existing_tags, new_tags = _tag_usage(db, uid, tags)
    if existing_tags + new_tags > limits["tags"]:
        return _error("too_many_tags", 413, limit=limits["tags"])
    if not data.get("allow_duplicate"):
        # A closed Secret group is invisible: links inside it must not
        # surface through the duplicate check (no 409, no title leak).
        secret_filter = ""
        if secret_locked(db, uid):
            secret_filter = " AND (g.kind IS NULL OR g.kind <> 'secret')"
        duplicate = db.execute(
            f"""
            SELECT b.id, b.title, g.name AS group_name
            FROM bookmarks b LEFT JOIN groups g ON g.id = b.group_id
            WHERE b.user_id = ? AND b.url = ? AND b.deleted_at IS NULL
            {secret_filter}
            ORDER BY b.id LIMIT 1
            """,
            (uid, url),
        ).fetchone()
        if duplicate is not None:
            return _error(
                "duplicate",
                409,
                existing={
                    "id": duplicate["id"],
                    "title": duplicate["title"],
                    "group_name": duplicate["group_name"],
                },
            )
    favorite = 1 if group is not None and group["kind"] == "favorites" else 0
    now = iso()
    cursor = db.execute(
        "INSERT INTO bookmarks(user_id, group_id, url, title, description, favorite, pinned,"
        " visits, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (
            uid,
            group["id"] if group else None,
            url,
            title,
            description,
            favorite,
            1 if data.get("pinned") else 0,
            now,
            now,
        ),
    )
    bookmark_id = int(cursor.lastrowid)
    _set_tags(db, uid, bookmark_id, tags)
    db.commit()
    row = _fetch_bookmark(db, uid, bookmark_id)
    return jsonify({"bookmark": _bookmark_payload(db, row)}), 201


@bp.get("/bookmarks/<int:bookmark_id>")
def get_bookmark(bookmark_id: int):
    db = _db()
    row = _fetch_bookmark(db, _uid(), bookmark_id)
    if row is None:
        return _error("not_found", 404)
    return jsonify({"bookmark": _bookmark_payload(db, row)})


@bp.patch("/bookmarks/<int:bookmark_id>")
def update_bookmark(bookmark_id: int):
    db = _db()
    uid = _uid()
    row = _fetch_bookmark(db, uid, bookmark_id)
    if row is None:
        return _error("not_found", 404)
    data = _json()
    fields: dict[str, object] = {}
    if "url" in data:
        try:
            fields["url"] = normalize_url(str(data.get("url") or ""))
        except ValueError as exc:
            return _error("invalid_url", 400, message=str(exc))
    if "title" in data:
        fields["title"] = clean_text(data.get("title"), 300) or guess_title(
            str(fields.get("url") or row["url"])
        )
    if "description" in data:
        fields["description"] = clean_text(data.get("description"), 2000, multiline=True)
    if "pinned" in data:
        fields["pinned"] = 1 if data.get("pinned") else 0
    if "icon" in data:
        raw_icon = data.get("icon")
        if raw_icon in (None, ""):
            fields["icon"] = None
        else:
            icon_uri = validate_image_data_uri(raw_icon)
            if icon_uri is None:
                return _error("invalid_icon", 400)
            fields["icon"] = icon_uri
    if "group_id" in data:
        group = _get_group(db, uid, data.get("group_id"))
        if data.get("group_id") not in (None, "", 0, "0") and group is None:
            return _error("group_not_found", 404)
        if group is not None and group["kind"] == "secret" and secret_locked(db, uid):
            return _error("secret_locked_group", 403)
        fields["group_id"] = group["id"] if group else None
        is_favorite_group = group is not None and group["kind"] == "favorites"
        fields["favorite"] = 1 if is_favorite_group else 0
        if not is_favorite_group:
            # A link moved out of Favorites is a standalone bookmark again.
            fields["origin_id"] = None
    if "tags" in data:
        tags = parse_tags(data.get("tags"))
        existing_tags, new_tags = _tag_usage(db, uid, tags)
        tag_limit = _user_limits(db, uid)["tags"]
        if existing_tags + new_tags > tag_limit:
            return _error("too_many_tags", 413, limit=tag_limit)
        _set_tags(db, uid, bookmark_id, tags)
    if fields:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        db.execute(
            f"UPDATE bookmarks SET {assignments}, updated_at = ? WHERE id = ?",
            (*fields.values(), iso(), bookmark_id),
        )
    else:
        db.execute("UPDATE bookmarks SET updated_at = ? WHERE id = ?", (iso(), bookmark_id))
    db.commit()
    row = _fetch_bookmark(db, uid, bookmark_id)
    return jsonify({"bookmark": _bookmark_payload(db, row)})


@bp.delete("/bookmarks/<int:bookmark_id>")
def delete_bookmark(bookmark_id: int):
    db = _db()
    row = _fetch_bookmark(db, _uid(), bookmark_id)
    if row is None:
        return _error("not_found", 404)
    db.execute(
        "UPDATE bookmarks SET deleted_at = ? WHERE id = ? AND user_id = ?",
        (iso(), bookmark_id, _uid()),
    )
    db.commit()
    return jsonify({"ok": True, "id": bookmark_id})


@bp.post("/bookmarks/<int:bookmark_id>/restore")
def restore_bookmark(bookmark_id: int):
    db = _db()
    uid = _uid()
    row = _fetch_bookmark(db, uid, bookmark_id)
    if row is None:
        return _error("not_found", 404)
    db.execute(
        "UPDATE bookmarks SET deleted_at = NULL WHERE id = ? AND user_id = ?", (bookmark_id, uid)
    )
    db.commit()
    row = _fetch_bookmark(db, uid, bookmark_id)
    return jsonify({"bookmark": _bookmark_payload(db, row)})


@bp.delete("/bookmarks/<int:bookmark_id>/purge")
def purge_bookmark(bookmark_id: int):
    db = _db()
    uid = _uid()
    row = _fetch_bookmark(db, uid, bookmark_id)
    if row is None:
        return _error("not_found", 404)
    db.execute("DELETE FROM bookmarks WHERE id = ? AND user_id = ?", (bookmark_id, uid))
    # Favourite copies of a purged link become standalone favorites.
    db.execute(
        "UPDATE bookmarks SET origin_id = NULL WHERE origin_id = ? AND user_id = ?",
        (bookmark_id, uid),
    )
    db.commit()
    return jsonify({"ok": True, "id": bookmark_id})


def _remove_favorite_copy(db, user_id: int, row) -> None:
    """Drop a favourites copy; keep it recoverable if its source is gone."""
    origin_id = row["origin_id"]
    origin = None
    if origin_id:
        origin = db.execute(
            "SELECT 1 FROM bookmarks WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (origin_id, user_id),
        ).fetchone()
    if origin is not None:
        db.execute("DELETE FROM bookmarks WHERE id = ? AND user_id = ?", (row["id"], user_id))
    else:
        db.execute(
            "UPDATE bookmarks SET deleted_at = ? WHERE id = ? AND user_id = ?",
            (iso(), row["id"], user_id),
        )
    db.commit()


@bp.post("/bookmarks/<int:bookmark_id>/favorite")
def toggle_favorite(bookmark_id: int):
    db = _db()
    uid = _uid()
    row = _fetch_bookmark(db, uid, bookmark_id)
    if row is None:
        return _error("not_found", 404)
    favorites = _favorites_group(db, uid)

    # A card inside the Favorites group is itself the saved copy.
    if row["group_id"] == favorites["id"] or row["group_kind"] == "favorites":
        _remove_favorite_copy(db, uid, row)
        return jsonify({"favorited": False, "removed": True, "id": bookmark_id})

    copy = db.execute(
        "SELECT id FROM bookmarks WHERE user_id = ? AND origin_id = ? AND group_id = ?"
        " AND deleted_at IS NULL LIMIT 1",
        (uid, bookmark_id, favorites["id"]),
    ).fetchone()
    if copy is not None:
        db.execute("DELETE FROM bookmarks WHERE id = ? AND user_id = ?", (copy["id"], uid))
        db.commit()
        return jsonify({"favorited": False, "removed": True, "id": copy["id"]})

    now = iso()
    cursor = db.execute(
        "INSERT INTO bookmarks(user_id, group_id, url, title, description, favorite, origin_id,"
        " pinned, visits, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, 0, 0, ?, ?)",
        (uid, favorites["id"], row["url"], row["title"], row["description"], bookmark_id, now, now),
    )
    copy_id = int(cursor.lastrowid)
    _set_tags(db, uid, copy_id, _tags_for(db, [bookmark_id]).get(bookmark_id, []))
    db.commit()
    return jsonify({"favorited": True, "copy_id": copy_id, "id": bookmark_id})


def _secret_bulk_filter(db, user_id: int) -> tuple[str, list]:
    """SQL fragment that keeps a closed Secret group out of bulk operations."""
    if not secret_locked(db, user_id):
        return "", []
    return (
        " AND (group_id IS NULL OR group_id NOT IN"
        " (SELECT id FROM groups WHERE user_id = ? AND kind = 'secret'))",
        [user_id],
    )


@bp.post("/trash/empty")
def empty_trash():
    db = _db()
    uid = _uid()
    exclude, extra = _secret_bulk_filter(db, uid)
    rows = db.execute(
        "SELECT COUNT(*) c FROM bookmarks WHERE user_id = ? AND deleted_at IS NOT NULL"
        + exclude,
        (uid, *extra),
    ).fetchone()
    db.execute(
        "UPDATE bookmarks SET origin_id = NULL WHERE user_id = ? AND origin_id IN"
        " (SELECT id FROM bookmarks WHERE user_id = ? AND deleted_at IS NOT NULL"
        + exclude
        + ")",
        (uid, uid, *extra),
    )
    db.execute(
        "DELETE FROM bookmarks WHERE user_id = ? AND deleted_at IS NOT NULL" + exclude,
        (uid, *extra),
    )
    db.commit()
    return jsonify({"ok": True, "deleted": rows["c"]})


@bp.post("/trash/restore-all")
def restore_all():
    db = _db()
    uid = _uid()
    # Links of a closed Secret group stay in the trash until it is unlocked.
    exclude, extra = _secret_bulk_filter(db, uid)
    rows = db.execute(
        "SELECT COUNT(*) c FROM bookmarks WHERE user_id = ? AND deleted_at IS NOT NULL"
        + exclude,
        (uid, *extra),
    ).fetchone()
    db.execute(
        "UPDATE bookmarks SET deleted_at = NULL WHERE user_id = ? AND deleted_at IS NOT NULL"
        + exclude,
        (uid, *extra),
    )
    db.commit()
    return jsonify({"ok": True, "restored": rows["c"]})


# ---------------------------------------------------------------------------
# Tags & statistics
# ---------------------------------------------------------------------------


@bp.get("/tags")
def list_tags():
    db = _db()
    uid = _uid()
    # Tags of a closed Secret group stay invisible, together with its links.
    exclude = (
        " AND (g.kind IS NULL OR g.kind <> 'secret')" if secret_locked(db, uid) else ""
    )
    rows = db.execute(
        f"""
        SELECT t.id, t.name, COUNT(b.id) AS count
        FROM tags t
        JOIN bookmark_tags bt ON bt.tag_id = t.id
        JOIN bookmarks b ON b.id = bt.bookmark_id AND b.deleted_at IS NULL
        LEFT JOIN groups g ON g.id = b.group_id
        WHERE t.user_id = ? AND b.user_id = ?{exclude}
        GROUP BY t.id, t.name
        HAVING COUNT(b.id) > 0
        ORDER BY count DESC, t.name COLLATE NOCASE
        """,
        (uid, uid),
    ).fetchall()
    return jsonify(
        {"tags": [{"id": row["id"], "name": row["name"], "count": row["count"]} for row in rows]}
    )


@bp.delete("/tags/<int:tag_id>")
def delete_tag(tag_id: int):
    db = _db()
    row = db.execute(
        "SELECT id FROM tags WHERE id = ? AND user_id = ?", (tag_id, _uid())
    ).fetchone()
    if row is None:
        return _error("not_found", 404)
    db.execute("DELETE FROM tags WHERE id = ? AND user_id = ?", (tag_id, _uid()))
    db.commit()
    return jsonify({"ok": True})


@bp.get("/stats")
def stats():
    db = _db()
    uid = _uid()
    # Counters mirror what the interface actually shows: links of a closed
    # Secret group are not counted anywhere.
    exclude = (
        " AND (g.kind IS NULL OR g.kind <> 'secret')" if secret_locked(db, uid) else ""
    )
    row = db.execute(
        f"""
        SELECT
            (SELECT COUNT(*) FROM bookmarks b LEFT JOIN groups g ON g.id = b.group_id
                WHERE b.user_id = ? AND b.deleted_at IS NULL{exclude}) AS bookmarks,
            (SELECT COUNT(*) FROM bookmarks b LEFT JOIN groups g ON g.id = b.group_id
                WHERE b.user_id = ? AND b.deleted_at IS NOT NULL{exclude}) AS trash,
            (SELECT COUNT(*) FROM groups WHERE user_id = ? AND kind = 'custom') AS groups,
            (SELECT COUNT(DISTINCT t.id) FROM tags t
                JOIN bookmark_tags bt ON bt.tag_id = t.id
                JOIN bookmarks b ON b.id = bt.bookmark_id AND b.deleted_at IS NULL
                LEFT JOIN groups g ON g.id = b.group_id
                WHERE t.user_id = ?{exclude}) AS tags,
            (SELECT COALESCE(SUM(b.visits), 0) FROM bookmarks b
                LEFT JOIN groups g ON g.id = b.group_id
                WHERE b.user_id = ? AND b.deleted_at IS NULL{exclude}) AS visits,
            (SELECT COUNT(*) FROM bookmarks b JOIN groups g ON g.id = b.group_id
                WHERE b.user_id = ? AND g.kind = 'favorites' AND b.deleted_at IS NULL) AS favorites
        """,
        (uid, uid, uid, uid, uid, uid),
    ).fetchone()
    return jsonify(dict(row))


@bp.get("/settings")
def get_settings():
    return jsonify({"settings": load_settings(g.user["settings"])})


@bp.put("/settings")
def put_settings():
    data = _json()
    current = load_settings(g.user["settings"])
    merged = normalize_settings(data, base=current)
    db = _db()
    db.execute(
        "UPDATE users SET settings = ? WHERE id = ?",
        (json.dumps(merged, ensure_ascii=False), _uid()),
    )
    db.commit()
    g.user["settings"] = json.dumps(merged)
    return jsonify({"settings": merged})


# ---------------------------------------------------------------------------
# Auto-updates (GitHub). Admin only; update.py (project root) does the work.
# ---------------------------------------------------------------------------


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _import_updater():
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    import update as updater  # noqa: PLC0415 - stdlib only, lives at the root

    return updater


def _read_pid(path: str) -> int | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        )
        return f"[{pid}]" in proc.stdout or str(pid) in proc.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@bp.get("/update/check")
def update_check():
    if not g.user["is_admin"]:
        return _error("forbidden", 403)
    try:
        updater = _import_updater()
    except ImportError:
        return _error("updater_missing", 500)
    latest = updater.fetch_latest()
    if latest is None:
        return _error("github_unreachable", 502)
    current = updater.current_version()
    available = (updater.parse_version(latest["version"]) or (0,)) > (
        updater.parse_version(current) or (0,)
    )
    return jsonify(
        {
            "current": current,
            "latest": latest["version"],
            "available": available,
            "source": latest["source"],
        }
    )


@bp.post("/update/run")
def update_run():
    if not g.user["is_admin"]:
        return _error("forbidden", 403)
    data_dir = current_app.config["DATA_DIR"]
    root = _project_root()
    pid_file = os.path.join(data_dir, "update.pid")
    pid = _read_pid(pid_file)
    if pid is not None and _pid_alive(pid):
        return _error("already_running", 409)
    if not os.path.exists(os.path.join(root, "update.py")):
        return _error("updater_missing", 500)
    log_file = open(os.path.join(data_dir, "update.log"), "ab")
    kwargs: dict = dict(cwd=root, stdout=log_file, stderr=subprocess.STDOUT)
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000010 | 0x00000200  # detached process
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen([sys.executable, "update.py", "--yes"], **kwargs)
    except OSError as exc:
        log_file.close()
        return _error("start_failed", 500, detail=str(exc))
    log_file.close()
    with open(pid_file, "w", encoding="utf-8") as handle:
        handle.write(str(proc.pid))
    return jsonify({"started": True, "pid": proc.pid})


# ---------------------------------------------------------------------------
# Page metadata & favicons
# ---------------------------------------------------------------------------

_meta_cache: dict[str, tuple[float, dict]] = {}
_meta_lock = threading.Lock()
_icon_locks: dict[str, threading.Lock] = {}
_icon_locks_guard = threading.Lock()
# How long to re-try a favicon that failed to download (seconds).
FAVICON_NEGATIVE_TTL = 3600


def _icon_lock(key: str) -> threading.Lock:
    with _icon_locks_guard:
        lock = _icon_locks.get(key)
        if lock is None:
            lock = _icon_locks[key] = threading.Lock()
        return lock


@bp.get("/metadata")
def page_metadata():
    try:
        url = normalize_url(request.args.get("url") or "")
    except ValueError:
        return _error("invalid_url")
    now = time.time()
    with _meta_lock:
        cached = _meta_cache.get(url)
    if cached and now - cached[0] < 3600:
        return jsonify(cached[1])
    info = fetch_page_metadata(url)
    info.setdefault("title", "")
    info.setdefault("description", "")
    with _meta_lock:
        if len(_meta_cache) > 400:
            _meta_cache.clear()
        _meta_cache[url] = (now, info)
    return jsonify(info)


@bp.get("/icon")
def favicon():
    try:
        page_url = normalize_url(request.args.get("u") or request.args.get("url") or "")
    except ValueError:
        return ("", 404)
    parts = urllib.parse.urlsplit(page_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    key = hashlib.sha256(origin.encode("utf-8")).hexdigest()
    directory = current_app.config["ICON_DIR"]
    meta_path = os.path.join(directory, key + ".json")
    data_path = os.path.join(directory, key + ".bin")

    def read_meta():
        try:
            with open(meta_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def serve_or_empty(meta):
        if meta and meta.get("ok") and os.path.exists(data_path):
            mimetype = meta.get("mime") or "image/png"
            headers: dict[str, str] = {}
            if mimetype == "image/svg+xml":
                # SVG is XML and can carry scripts or external requests.
                # As a download it cannot render; inside <img> the sandbox
                # strips scripts and default-src 'none' blocks resources.
                headers["Content-Disposition"] = f'attachment; filename="{key}.svg"'
                headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
            return send_file(data_path, mimetype=mimetype, max_age=604800, headers=headers)
        return ("", 204, {"Cache-Control": f"public, max-age={FAVICON_NEGATIVE_TTL}"})

    meta = read_meta()
    if meta:
        age = time.time() - float(meta.get("ts") or 0)
        if meta.get("ok") or age < FAVICON_NEGATIVE_TTL:
            return serve_or_empty(meta)

    lock = _icon_lock(key)
    if not lock.acquire(blocking=False):
        return serve_or_empty(read_meta())
    try:
        meta = read_meta()
        if meta and (meta.get("ok") or time.time() - float(meta.get("ts") or 0) < FAVICON_NEGATIVE_TTL):
            return serve_or_empty(meta)
        result = fetch_favicon(page_url)
        meta = {"ts": time.time(), "ok": False, "mime": ""}
        if result:
            payload, mime = result
            try:
                with open(data_path, "wb") as handle:
                    handle.write(payload)
                meta = {"ts": time.time(), "ok": True, "mime": mime}
            except OSError:
                meta = {"ts": time.time(), "ok": False, "mime": ""}
        try:
            with open(meta_path, "w", encoding="utf-8") as handle:
                json.dump(meta, handle)
        except OSError:
            pass
        return serve_or_empty(meta)
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# Export / import
# ---------------------------------------------------------------------------


def _xml_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@bp.get("/export")
def export_data():
    fmt = (request.args.get("format") or "json").lower()
    db = _db()
    uid = _uid()
    group_rows = db.execute(
        "SELECT * FROM groups WHERE user_id = ? ORDER BY position, id", (uid,)
    ).fetchall()
    rows = db.execute(
        BOOKMARK_SELECT
        + " WHERE b.user_id = ? AND b.deleted_at IS NULL"
        + " ORDER BY b.created_at ASC, b.id ASC",
        (uid,),
    ).fetchall()
    if secret_locked(db, uid):
        # A closed Secret group is not exported at all: the backup must not
        # leak the links the user is currently hiding.
        group_rows = [row for row in group_rows if row["kind"] != "secret"]
        rows = [row for row in rows if row["group_kind"] != "secret"]
    group_names = {row["id"]: row["name"] for row in group_rows}
    tags = _tags_for(db, [row["id"] for row in rows])
    stamp = iso()[:10]

    if fmt == "html":
        lines = [
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
            '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
            "<TITLE>Bookmarks</TITLE>",
            "<H1>Bookmarks</H1>",
            "<DL><p>",
        ]

        def link_lines(row) -> list[str]:
            tags_attr = ",".join(tags.get(row["id"], []))
            created = parse_iso(row["created_at"])
            add_date = int(created.timestamp()) if created else int(time.time())
            result = [
                f'        <DT><A HREF="{_xml_escape(row["url"])}"'
                f' ADD_DATE="{add_date}"'
                f' TAGS="{_xml_escape(tags_attr)}">{_xml_escape(row["title"])}</A>'
            ]
            if row["description"]:
                result.append(f"        <DD>{_xml_escape(row['description'])}")
            return result

        for group in group_rows:
            name = "Favorites" if group["kind"] == "favorites" else group["name"]
            lines.append(f"    <DT><H3>{_xml_escape(name)}</H3>")
            lines.append("    <DL><p>")
            for row in rows:
                if row["group_id"] == group["id"]:
                    lines.extend(link_lines(row))
            lines.append("    </DL><p>")

        ungrouped = [row for row in rows if row["group_id"] is None]
        if ungrouped:
            # Links without a group must survive the export as well.
            lines.append("    <DT><H3>Unsorted</H3>")
            lines.append("    <DL><p>")
            for row in ungrouped:
                lines.extend(link_lines(row))
            lines.append("    </DL><p>")

        lines.append("</DL><p>")
        payload = "\n".join(lines).encode("utf-8")
        return send_file(
            io.BytesIO(payload),
            mimetype="text/html; charset=utf-8",
            as_attachment=True,
            download_name=f"bookmarks-{stamp}.html",
        )

    # Full backup (v2): the profile, the settings (quick links included) and
    # the Secret password travel with the links, so a restore recreates the
    # whole interface, not just the list of bookmarks.
    user_row = db.execute(
        "SELECT display_name, avatar_color, avatar_photo, settings FROM users WHERE id = ?",
        (uid,),
    ).fetchone()
    payload = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "export_version": 2,
        "exported_at": iso(),
        "user": {
            "display_name": user_row["display_name"],
            "avatar_color": user_row["avatar_color"],
            "avatar_photo": user_row["avatar_photo"],
        },
        "settings": load_settings(user_row["settings"]),
        "groups": [
            {
                "name": "Favorites" if row["kind"] == "favorites" else row["name"],
                "icon": row["icon"],
                "kind": row["kind"],
                **(
                    {"password_hash": row["password_hash"]}
                    if row["kind"] == "secret" and row["password_hash"]
                    else {}
                ),
            }
            for row in group_rows
        ],
        "bookmarks": [
            {
                "url": row["url"],
                "title": row["title"],
                "description": row["description"],
                "tags": tags.get(row["id"], []),
                "group": group_names.get(row["group_id"]),
                "favorite": bool(row["favorite"]),
                "pinned": bool(row["pinned"]),
                "icon": row["icon"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "visits": row["visits"],
            }
            for row in rows
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return send_file(
        io.BytesIO(raw),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"bookmarks-{stamp}.json",
    )


class _NetscapeParser(__import__("html.parser", fromlist=["HTMLParser"]).HTMLParser):
    """Very small reader for Netscape bookmark files (browser exports)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.folders: list[tuple[int, str]] = []
        self.links: list[dict] = []
        self._h3: dict | None = None
        self._a: dict | None = None

    def _current_folder(self):
        return self.folders[-1][1] if self.folders else ""

    def handle_starttag(self, tag, attrs):
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag == "dl":
            self.depth += 1
        elif tag == "h3":
            self._h3 = {"depth": self.depth, "text": ""}
        elif tag == "a":
            self._a = {
                "href": values.get("href", ""),
                "title": "",
                "tags": values.get("tags", ""),
                "folder": self._current_folder(),
            }

    def handle_endtag(self, tag):
        if tag == "h3" and self._h3 is not None:
            text = " ".join(self._h3["text"].split())
            if text:
                self.folders.append((self._h3["depth"], text))
            self._h3 = None
        elif tag == "a" and self._a is not None:
            self._a["title"] = " ".join(self._a["title"].split())
            self.links.append(self._a)
            self._a = None
        elif tag == "dl":
            depth = self.depth
            while self.folders and self.folders[-1][0] >= depth - 1:
                self.folders.pop()
            self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        if self._h3 is not None:
            self._h3["text"] += data
        elif self._a is not None:
            self._a["title"] += data


def _parse_import(fmt: str, content: str):
    """Parse an import file into {"groups", "items", "user", "settings"}.

    "user" and "settings" (the v2 full-backup blocks) are None for HTML
    files and for v1 JSON exports that carry links only.
    """
    if fmt == "html":
        parser = _NetscapeParser()
        parser.feed(content)
        items = [
            {
                "url": link["href"],
                "title": link["title"],
                "tags": link["tags"],
                "group": link["folder"],
            }
            for link in parser.links
        ]
        folders: list[dict] = []
        seen = set()
        for item in items:
            name = clean_text(item.get("group"), 40)
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                folders.append({"name": name})
        return {"groups": folders, "items": items, "user": None, "settings": None}
    raw = json.loads(content)
    if isinstance(raw, list):
        return {"groups": [], "items": raw, "user": None, "settings": None}
    if not isinstance(raw, dict):
        raise ValueError("Unsupported JSON structure")
    items = raw.get("bookmarks")
    if not isinstance(items, list):
        raise ValueError("No bookmarks found in file")
    groups = raw.get("groups") if isinstance(raw.get("groups"), list) else []
    user = raw.get("user") if isinstance(raw.get("user"), dict) else None
    settings = raw.get("settings") if isinstance(raw.get("settings"), dict) else None
    return {"groups": groups, "items": items, "user": user, "settings": settings}


@bp.post("/import")
def import_data():
    data = _json()
    fmt = (data.get("format") or "json").lower()
    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        return _error("empty_file")
    if len(content) > 12_000_000:
        return _error("file_too_large", 413)
    try:
        parsed = _parse_import(fmt, content)
        group_specs, items = parsed["groups"], parsed["items"]
    except (ValueError, json.JSONDecodeError):
        return _error("invalid_file")
    default_group = clean_text(data.get("group_name"), 40)

    db = _db()
    uid = _uid()
    existing = {
        row["url"]
        for row in db.execute(
            "SELECT url FROM bookmarks WHERE user_id = ? AND deleted_at IS NULL", (uid,)
        ).fetchall()
    }
    groups: dict[str, object] = {}
    reserved: set[str] = {"favorites", "secret"}
    for row in db.execute("SELECT * FROM groups WHERE user_id = ?", (uid,)).fetchall():
        groups[row["name"].casefold()] = row
        reserved.add(row["name"].casefold())
    if secret_locked(db, uid):
        # Importing into a closed Secret group would make the links vanish
        # silently; leave them ungrouped instead and never recreate the
        # built-in group under a different kind.
        groups = {key: row for key, row in groups.items() if row["kind"] != "secret"}
    favorites = _favorites_group(db, uid)
    groups.setdefault("favorites", favorites)
    position = db.execute(
        "SELECT COALESCE(MAX(position), 0) AS p FROM groups WHERE user_id = ?", (uid,)
    ).fetchone()["p"]
    created_groups = 0
    secret_hash: str | None = None
    for spec in group_specs:
        if not isinstance(spec, dict):
            continue
        if spec.get("kind") == "secret" and isinstance(spec.get("password_hash"), str):
            # The Secret group is not re-created, but a full backup carries
            # its password hash so the restore keeps the same protection.
            secret_hash = spec["password_hash"][:512] or None
        name = clean_text(spec.get("name"), 40)
        if not name:
            continue
        key = name.casefold()
        if key in groups:
            continue
        if spec.get("kind") in ("favorites", "secret"):
            # Built-in groups are represented by the existing ones only.
            continue
        if key in reserved or created_groups >= 80:
            continue
        position += 1
        icon = clean_text(spec.get("icon"), 8) or "📁"
        cursor = db.execute(
            "INSERT INTO groups(user_id, name, icon, kind, position, created_at)"
            " VALUES (?, ?, ?, 'custom', ?, ?)",
            (uid, name, icon, position, iso()),
        )
        groups[key] = dict(db.execute("SELECT * FROM groups WHERE id = ?", (cursor.lastrowid,)).fetchone())
        created_groups += 1

    imported = 0
    skipped = 0
    now = iso()
    for item in items[:MAX_IMPORT_ITEMS]:
        if not isinstance(item, dict):
            skipped += 1
            continue
        try:
            url = normalize_url(str(item.get("url") or ""))
        except ValueError:
            skipped += 1
            continue
        if url in existing:
            skipped += 1
            continue
        group_name = item.get("group") or item.get("folder") or default_group or ""
        group = groups.get(str(group_name).casefold()) if group_name else None
        if group is None and item.get("favorite"):
            group = favorites
        title = clean_text(item.get("title"), 300) or guess_title(url)
        description = clean_text(item.get("description"), 2000, multiline=True)
        tags = parse_tags(item.get("tags"))
        icon_uri = validate_image_data_uri(item.get("icon"))
        raw_visits = item.get("visits")
        visits = 0
        if isinstance(raw_visits, (int, float)) and not isinstance(raw_visits, bool):
            visits = max(0, min(1_000_000_000, int(raw_visits)))
        created = parse_iso(item.get("created_at")) if isinstance(item.get("created_at"), str) else None
        cursor = db.execute(
            "INSERT INTO bookmarks(user_id, group_id, url, title, description, favorite, pinned,"
            " visits, created_at, updated_at, icon) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                uid,
                group["id"] if group else None,
                url,
                title,
                description,
                1 if group is not None and group["kind"] == "favorites" else 0,
                1 if item.get("pinned") else 0,
                visits,
                iso(created) if created else now,
                now,
                icon_uri,
            ),
        )
        _set_tags(db, uid, int(cursor.lastrowid), tags)
        existing.add(url)
        imported += 1

    # v2 full backup: restore the settings (quick links included) and the
    # profile, so the interface looks exactly like the one that was backed up.
    settings_applied = False
    profile_applied = False
    secret_restored = False
    restored_settings: dict[str, object] | None = None
    if parsed["settings"] is not None:
        restored_settings = normalize_settings(parsed["settings"])
        db.execute(
            "UPDATE users SET settings = ? WHERE id = ?",
            (json.dumps(restored_settings, ensure_ascii=False), uid),
        )
        settings_applied = True
    user_block = parsed["user"]
    if user_block:
        updates: list[str] = []
        values: list = []
        name = str(user_block.get("display_name") or "").strip()[:48]
        if name:
            updates.append("display_name = ?")
            values.append(name)
        color = str(user_block.get("avatar_color") or "").strip()
        if is_valid_color(color):
            updates.append("avatar_color = ?")
            values.append(color)
        if "avatar_photo" in user_block:
            photo = user_block["avatar_photo"]
            if not photo:
                updates.append("avatar_photo = NULL")
            else:
                photo_uri = validate_image_data_uri(photo, max_bytes=1 * 1024 * 1024)
                if photo_uri:
                    updates.append("avatar_photo = ?")
                    values.append(photo_uri)
        if updates:
            db.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?", (*values, uid)
            )
            profile_applied = True
    if secret_hash:
        secret_group = db.execute(
            "SELECT * FROM groups WHERE user_id = ? AND kind = 'secret'", (uid,)
        ).fetchone()
        # Same rule as the API: a closed Secret group only changes its
        # password from an unlocked session (or when it has none yet).
        if secret_group is not None and (
            secret_group["password_hash"] is None or not secret_locked(db, uid)
        ):
            db.execute(
                "UPDATE groups SET password_hash = ? WHERE id = ? AND user_id = ?",
                (secret_hash, secret_group["id"], uid),
            )
            # The restored password is the one from now on: re-lock the
            # group in every session of the user.
            db.execute(
                "UPDATE sessions SET secret_unlocked = 0, secret_unlocked_at = NULL"
                " WHERE user_id = ?",
                (uid,),
            )
            secret_restored = True
    db.commit()

    result: dict[str, object] = {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "groups_created": created_groups,
        "settings_applied": settings_applied,
        "profile_applied": profile_applied,
        "secret_password_restored": secret_restored,
    }
    if restored_settings is not None:
        result["settings"] = restored_settings
    if profile_applied:
        row = db.execute(
            "SELECT display_name, avatar_color, avatar_photo FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
        result["user"] = {
            "display_name": row["display_name"],
            "avatar_color": row["avatar_color"],
            "avatar_photo": row["avatar_photo"],
        }
    return jsonify(result)

