"""Admin panel API: global statistics and the user directory.

All endpoints require an authenticated admin (users.is_admin = 1).
The first account of an installation is created as an admin; further
admins are granted from the panel itself or with ``manage.py make-admin``.
"""

from __future__ import annotations

import os
import time
from datetime import timedelta
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

from .db import SCHEMA_VERSION, get_db
from .util import (
    APP_VERSION,
    LIMIT_BOUNDS,
    MAX_BOOKMARKS_PER_USER,
    MAX_GROUPS_PER_USER,
    MAX_TAGS_PER_USER,
    hash_password,
    hash_token,
    iso,
    utcnow,
)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

# Process start, used for the uptime figure in the summary.
START_MONOTONIC = time.monotonic()


def admin_required(view):
    """Allow only logged-in admins; everyone else sees the usual codes."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        user = g.get("user")
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        if not user["is_admin"]:
            return jsonify({"error": "not_admin"}), 403
        return view(*args, **kwargs)

    return wrapper


def _json() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _user_row(db, user_id: int):
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def _user_payload(db, row) -> dict:
    uid = row["id"]
    bookmarks = db.execute(
        "SELECT COUNT(*) c FROM bookmarks WHERE user_id = ? AND deleted_at IS NULL", (uid,)
    ).fetchone()["c"]
    trash = db.execute(
        "SELECT COUNT(*) c FROM bookmarks WHERE user_id = ? AND deleted_at IS NOT NULL", (uid,)
    ).fetchone()["c"]
    groups = db.execute(
        "SELECT COUNT(*) c FROM groups WHERE user_id = ? AND kind = 'custom'", (uid,)
    ).fetchone()["c"]
    tags = db.execute("SELECT COUNT(*) c FROM tags WHERE user_id = ?", (uid,)).fetchone()["c"]
    sessions = db.execute(
        "SELECT COUNT(*) c FROM sessions WHERE user_id = ?", (uid,)
    ).fetchone()["c"]
    return {
        "id": uid,
        "username": row["username"],
        "display_name": row["display_name"],
        "avatar_color": row["avatar_color"],
        "avatar_photo": row["avatar_photo"],
        "is_admin": bool(row["is_admin"]),
        "disabled": bool(row["disabled"]),
        "created_at": row["created_at"],
        "last_login": row["last_login"],
        "bookmarks": bookmarks,
        "trash": trash,
        "groups": groups,
        "tags": tags,
        "sessions": sessions,
        "limits": {
            "bookmarks": int(row["max_bookmarks"] or MAX_BOOKMARKS_PER_USER),
            "tags": int(row["max_tags"] or MAX_TAGS_PER_USER),
            "groups": int(row["max_groups"] or MAX_GROUPS_PER_USER),
        },
        "custom_limits": {
            "bookmarks": row["max_bookmarks"],
            "tags": row["max_tags"],
            "groups": row["max_groups"],
        },
    }


@bp.get("/summary")
@admin_required
def summary():
    db = get_db()
    active_since = iso(utcnow() - timedelta(days=30))
    rows = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM users) AS users_total,
            (SELECT COUNT(*) FROM users WHERE disabled = 1) AS users_disabled,
            (SELECT COUNT(*) FROM users WHERE last_login IS NOT NULL
                AND last_login >= ?) AS users_active_30d,
            (SELECT COUNT(*) FROM bookmarks WHERE deleted_at IS NULL) AS bookmarks,
            (SELECT COUNT(*) FROM bookmarks WHERE deleted_at IS NOT NULL) AS trash,
            (SELECT COUNT(*) FROM groups WHERE kind = 'custom') AS groups,
            (SELECT COUNT(*) FROM tags) AS tags
        """,
        (active_since,),
    ).fetchone()
    try:
        db_size = os.path.getsize(current_app.config["DATABASE"])
    except OSError:
        db_size = 0
    return jsonify(
        {
            **dict(rows),
            "db_size_bytes": db_size,
            "version": APP_VERSION,
            "schema": SCHEMA_VERSION,
            "uptime_seconds": int(time.monotonic() - START_MONOTONIC),
        }
    )


@bp.get("/users")
@admin_required
def list_users():
    db = get_db()
    rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    return jsonify(
        {
            "users": [_user_payload(db, row) for row in rows],
            "defaults": {
                "bookmarks": MAX_BOOKMARKS_PER_USER,
                "tags": MAX_TAGS_PER_USER,
                "groups": MAX_GROUPS_PER_USER,
            },
        }
    )


def _parse_limit(raw, kind: str) -> int | None | tuple:
    """Normalise an admin-supplied quota override.

    Returns (value, None) on success — value may be None (back to the
    global default) — or (None, error) on failure.
    """
    if raw is None:
        return None, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, "invalid_limit"
    low, high = LIMIT_BOUNDS[kind]
    if not low <= value <= high:
        return None, "invalid_limit"
    return value, None


@bp.patch("/users/<int:user_id>")
@admin_required
def update_user(user_id: int):
    data = _json()
    db = get_db()
    row = _user_row(db, user_id)
    if row is None:
        return jsonify({"error": "user_not_found"}), 404
    me = int(g.user["id"])
    admins_count = db.execute(
        "SELECT COUNT(*) c FROM users WHERE is_admin = 1"
    ).fetchone()["c"]

    updates: dict[str, object] = {}
    if "is_admin" in data:
        value = 1 if data["is_admin"] else 0
        if value == 0 and row["is_admin"] and admins_count == 1:
            # Demoting oneself is fine while another admin exists; the
            # last admin is refused so the panel never becomes unreachable.
            return jsonify({"error": "last_admin"}), 400
        updates["is_admin"] = value
    if "disabled" in data:
        value = 1 if data["disabled"] else 0
        if value == 1:
            # A blocked last admin makes the panel unreachable without a
            # CLI, so this is refused first (for the target as well).
            stays_admin = bool(data.get("is_admin", row["is_admin"]))
            if row["is_admin"] and stays_admin and admins_count == 1:
                return jsonify({"error": "last_admin"}), 400
            if user_id == me:
                # Locking oneself out requires another admin to unlock.
                return jsonify({"error": "cannot_change_self"}), 400
        updates["disabled"] = value

    for field in ("max_bookmarks", "max_tags", "max_groups"):
        if field not in data:
            continue
        kind = field.removeprefix("max_")
        value, problem = _parse_limit(data.get(field), kind)
        if problem:
            return jsonify({"error": problem}), 400
        updates[field] = value

    if not updates:
        return jsonify({"error": "nothing_to_update"}), 400
    assignments = ", ".join(f"{column} = ?" for column in updates)
    db.execute(
        f"UPDATE users SET {assignments} WHERE id = ?",
        (*updates.values(), user_id),
    )
    db.commit()
    row = _user_row(db, user_id)
    return jsonify({"user": _user_payload(db, row)})


@bp.post("/users/<int:user_id>/password")
@admin_required
def reset_password(user_id: int):
    data = _json()
    password = str(data.get("password") or "")
    if len(password) < 8:
        return jsonify({"error": "weak_password"}), 400
    if len(password) > 200:
        return jsonify({"error": "password_too_long"}), 400
    db = get_db()
    row = _user_row(db, user_id)
    if row is None:
        return jsonify({"error": "user_not_found"}), 404
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(password), user_id),
    )
    if user_id == int(g.user["id"]):
        # Keep the caller's own session, like a regular password change.
        token = request.cookies.get(current_app.config["SESSION_COOKIE"])
        db.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?",
            (user_id, hash_token(token or "")),
        )
    else:
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.commit()
    return jsonify({"ok": True})
