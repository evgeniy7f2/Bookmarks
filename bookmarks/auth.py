"""Registration, login, sessions and account settings."""

from __future__ import annotations

import os
import sqlite3
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

from . import ratelimit
from .db import get_db
from .settings import DEFAULT_SETTINGS, load_settings, normalize_settings
from .util import (
    MAX_BOOKMARKS_PER_USER,
    MAX_GROUPS_PER_USER,
    MAX_TAGS_PER_USER,
    SECRET_UNLOCK_TTL,
    days_from_now,
    hash_password,
    hash_token,
    is_valid_color,
    is_valid_username,
    iso,
    new_session_token,
    parse_iso,
    utcnow,
    validate_image_data_uri,
    verify_password,
)

bp = Blueprint("auth", __name__)


def _registration_open() -> bool:
    value = os.environ.get("BOOKMARKS_REGISTRATION", "").strip().lower()
    return value not in {"0", "false", "no", "closed", "off"}


def serialize_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "avatar_color": row["avatar_color"],
        "avatar_photo": row["avatar_photo"],
        "settings": load_settings(row["settings"]),
        "is_admin": bool(row["is_admin"]),
        "limits": {
            "bookmarks": int(row["max_bookmarks"] or MAX_BOOKMARKS_PER_USER),
            "tags": int(row["max_tags"] or MAX_TAGS_PER_USER),
            "groups": int(row["max_groups"] or MAX_GROUPS_PER_USER),
        },
        "created_at": row["created_at"],
        "last_login": row["last_login"],
    }


def _client_key() -> str:
    return f"ip:{request.remote_addr or 'unknown'}"


def _rate_limited(key: str) -> bool:
    return ratelimit.is_limited(key)


def _remember_attempt(key: str) -> None:
    ratelimit.remember(key)


def _clear_attempts(key: str) -> None:
    ratelimit.reset(key)


def _set_session_cookie(response, token: str, days: int | None):
    kwargs = {
        "httponly": True,
        "samesite": "Lax",
        "secure": bool(current_app.config.get("SESSION_COOKIE_SECURE")),
        "path": "/",
    }
    if days:
        kwargs["max_age"] = int(days * 86400)
    response.set_cookie(current_app.config["SESSION_COOKIE"], token, **kwargs)
    return response


def _clear_session_cookie(response):
    response.delete_cookie(
        current_app.config["SESSION_COOKIE"],
        path="/",
        httponly=True,
        samesite="Lax",
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")),
    )
    return response


def create_session(user_id: int, remember: bool = False):
    token = new_session_token()
    days = current_app.config["SESSION_REMEMBER_DAYS"] if remember else 0.5
    db = get_db()
    db.execute(
        "INSERT INTO sessions(token_hash, user_id, created_at, expires_at, ip, user_agent)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            hash_token(token),
            user_id,
            iso(),
            days_from_now(days),
            (request.remote_addr or "")[:64],
            (request.user_agent.string or "")[:300],
        ),
    )
    db.commit()
    return token, (days if remember else None)


@bp.before_app_request
def load_logged_in_user():
    g.user = None
    token = request.cookies.get(current_app.config["SESSION_COOKIE"])
    if not token:
        return
    db = get_db()
    row = db.execute(
        """
        SELECT u.id, u.username, u.display_name, u.password_hash, u.avatar_color,
               u.avatar_photo, u.settings, u.created_at, u.last_login, u.disabled,
               u.is_admin, u.max_bookmarks, u.max_tags, u.max_groups,
               s.expires_at, s.secret_unlocked, s.secret_unlocked_at
        FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?
        """,
        (hash_token(token),),
    ).fetchone()
    if row is None:
        return
    if row["expires_at"] <= iso():
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
        db.commit()
        return
    # A disabled account is logged out everywhere, instantly.
    if row["disabled"]:
        return
    g.user = dict(row)
    g.secret_unlocked = bool(row["secret_unlocked"])
    # The Secret group re-locks after SECRET_UNLOCK_TTL of inactivity; any
    # request refreshes the stamp (once it is at least half spent) so an
    # actively used browser stays open. An already-expired stamp is not
    # refreshed: the group stays closed until a fresh unlock.
    if g.secret_unlocked and row["secret_unlocked_at"]:
        unlocked_at = parse_iso(row["secret_unlocked_at"])
        if unlocked_at is not None and SECRET_UNLOCK_TTL / 2 < utcnow() - unlocked_at <= SECRET_UNLOCK_TTL:
            db.execute(
                "UPDATE sessions SET secret_unlocked_at = ? WHERE token_hash = ?",
                (iso(), hash_token(token)),
            )
            db.commit()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return jsonify({"error": "unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapped


def _default_groups(db, user_id: int) -> None:
    """Built-in groups every account starts with: Favorites and the
       password-protected Secret group (always listed right after Favorites)."""
    db.execute(
        "INSERT INTO groups(user_id, name, icon, kind, position, created_at)"
        " VALUES (?, 'Favorites', '🔥', 'favorites', 0, ?)",
        (user_id, iso()),
    )
    db.execute(
        "INSERT INTO groups(user_id, name, icon, kind, position, created_at)"
        " VALUES (?, 'Secret', '🔐', 'secret', 0, ?)",
        (user_id, iso()),
    )


def _validated_credentials(data: dict):
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username:
        return None, None, "username_required"
    if not password:
        return None, None, "password_required"
    return username, password, None


@bp.post("/api/auth/register")
def register():
    if not _registration_open():
        return jsonify({"error": "registration_closed"}), 403
    key = _client_key()
    if _rate_limited(key):
        return jsonify({"error": "rate_limited"}), 429
    data = request.get_json(silent=True) or {}
    username, password, error = _validated_credentials(data)
    if error:
        return jsonify({"error": error}), 400
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    if len(password) < 8:
        return jsonify({"error": "weak_password"}), 400
    if len(password) > 200:
        return jsonify({"error": "password_too_long"}), 400
    display_name = str(data.get("display_name") or "").strip()[:48] or username
    settings = normalize_settings({**DEFAULT_SETTINGS, "lang": data.get("lang") or "ru"})
    db = get_db()
    # The very first account of an installation becomes the admin (the same
    # rule the startup migration applies to pre-existing databases).
    first_user = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0
    try:
        cursor = db.execute(
            "INSERT INTO users(username, display_name, password_hash, avatar_color, settings,"
            " is_admin, created_at, last_login) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                username,
                display_name,
                hash_password(password),
                "#6366f1",
                __import__("json").dumps(settings, ensure_ascii=False),
                1 if first_user else 0,
                iso(),
                iso(),
            ),
        )
    except sqlite3.IntegrityError:
        _remember_attempt(key)
        return jsonify({"error": "username_taken"}), 409
    user_id = int(cursor.lastrowid)
    _default_groups(db, user_id)
    db.commit()
    _clear_attempts(key)
    token, days = create_session(user_id, remember=True)
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    response = jsonify({"user": serialize_user(row)})
    return _set_session_cookie(response, token, days or 30)


@bp.post("/api/auth/login")
def login():
    key = _client_key()
    data = request.get_json(silent=True) or {}
    username, password, error = _validated_credentials(data)
    if error:
        return jsonify({"error": error}), 400
    attempt_key = f"login|{key}|{username.casefold()}"
    if _rate_limited(attempt_key):
        return jsonify({"error": "rate_limited"}), 429
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        _remember_attempt(attempt_key)
        return jsonify({"error": "invalid_credentials"}), 401
    # Disabled accounts do not reveal anything about their password.
    if row["disabled"]:
        return jsonify({"error": "user_disabled"}), 403
    if not verify_password(password, row["password_hash"]):
        _remember_attempt(attempt_key)
        return jsonify({"error": "invalid_credentials"}), 401
    _clear_attempts(attempt_key)
    # Housekeeping on the hot path: expired sessions are removed as people
    # log in, so the table stays small even when the app idles for weeks.
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (iso(),))
    db.execute("UPDATE users SET last_login = ? WHERE id = ?", (iso(), row["id"]))
    db.commit()
    token, days = create_session(int(row["id"]), remember=bool(data.get("remember")))
    row = db.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    response = jsonify({"user": serialize_user(row)})
    return _set_session_cookie(response, token, days)


@bp.post("/api/auth/logout")
def logout():
    token = request.cookies.get(current_app.config["SESSION_COOKIE"])
    if token:
        db = get_db()
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
        db.commit()
    return _clear_session_cookie(jsonify({"ok": True}))


@bp.get("/api/auth/me")
def me():
    if g.get("user") is None:
        return jsonify({"user": None})
    return jsonify({"user": serialize_user(g.user)})


@bp.patch("/api/account")
@login_required
def update_account():
    user = g.user
    data = request.get_json(silent=True) or {}
    db = get_db()

    display_name = data.get("display_name")
    avatar_color = data.get("avatar_color")
    username = data.get("username")
    current_password = str(data.get("current_password") or "")
    new_password = str(data.get("new_password") or "")
    photo = data.get("photo")
    remove_photo = bool(data.get("remove_photo"))

    needs_password = (username and username.strip().casefold() != user["username"].casefold()) or bool(
        new_password
    )
    if needs_password:
        if not current_password:
            return jsonify({"error": "current_password_required"}), 400
        if not verify_password(current_password, user["password_hash"]):
            return jsonify({"error": "wrong_password"}), 403

    updates: dict[str, object] = {}
    if display_name is not None:
        name = str(display_name).strip()[:48]
        if not name:
            return jsonify({"error": "display_name_required"}), 400
        updates["display_name"] = name
    if avatar_color is not None:
        if not is_valid_color(str(avatar_color)):
            return jsonify({"error": "invalid_color"}), 400
        updates["avatar_color"] = str(avatar_color)
    if username is not None and username.strip().casefold() != user["username"].casefold():
        if not is_valid_username(username.strip()):
            return jsonify({"error": "invalid_username"}), 400
        updates["username"] = username.strip()
    if new_password:
        if len(new_password) < 8:
            return jsonify({"error": "weak_password"}), 400
        if new_password == current_password:
            return jsonify({"error": "password_unchanged"}), 400
        updates["password_hash"] = hash_password(new_password)
    if photo is not None or remove_photo:
        if remove_photo:
            updates["avatar_photo"] = None
        else:
            photo_uri = validate_image_data_uri(photo, max_bytes=1 * 1024 * 1024)
            if photo_uri is None:
                return jsonify({"error": "invalid_photo"}), 400
            updates["avatar_photo"] = photo_uri
    if not updates:
        return jsonify({"user": serialize_user(user)})

    assignments = ", ".join(f"{column} = ?" for column in updates)
    try:
        db.execute(f"UPDATE users SET {assignments} WHERE id = ?", (*updates.values(), user["id"]))
    except sqlite3.IntegrityError:
        return jsonify({"error": "username_taken"}), 409
    if "password_hash" in updates:
        token = request.cookies.get(current_app.config["SESSION_COOKIE"])
        db.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?",
            (user["id"], hash_token(token or "")),
        )
    db.commit()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    g.user = dict(row)
    return jsonify({"user": serialize_user(row)})


@bp.delete("/api/account")
@login_required
def delete_account():
    user = g.user
    data = request.get_json(silent=True) or {}
    if not verify_password(str(data.get("password") or ""), user["password_hash"]):
        return jsonify({"error": "wrong_password"}), 403
    if str(data.get("confirm") or "").strip().casefold() != user["username"].casefold():
        return jsonify({"error": "confirm_mismatch"}), 400
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    db.commit()
    return _clear_session_cookie(jsonify({"ok": True}))
