"""JSON API for groups, bookmarks, tags, metadata and data transfer."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.parse
from collections import defaultdict

from flask import Blueprint, current_app, g, jsonify, request, send_file

from .db import get_db
from .settings import DEFAULT_SETTINGS, load_settings, normalize_settings
from .util import (
    APP_NAME,
    APP_VERSION,
    FetchError,
    clean_text,
    fetch_favicon,
    fetch_page_metadata,
    guess_title,
    hash_password,
    hash_token,
    host_of,
    is_valid_color,
    iso,
    like_pattern,
    normalize_url,
    parse_iso,
    parse_tags,
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


def _fetch_bookmark(db, user_id: int, bookmark_id: int):
    return db.execute(
        BOOKMARK_SELECT + " WHERE b.id = ? AND b.user_id = ?", (bookmark_id, user_id)
    ).fetchone()


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
    the session row of the current cookie (survives reloads, per browser).
    """
    row = db.execute(
        "SELECT * FROM groups WHERE user_id = ? AND kind = 'secret' ORDER BY id LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None or not row["password_hash"]:
        return True
    token = request.cookies.get(current_app.config["SESSION_COOKIE"])
    if token:
        flag = db.execute(
            "SELECT secret_unlocked FROM sessions WHERE token_hash = ? AND user_id = ?",
            (hash_token(token), user_id),
        ).fetchone()
        return bool(flag and flag["secret_unlocked"])
    return False


def _set_secret_unlocked(db, user_id: int, value: int) -> None:
    token = request.cookies.get(current_app.config["SESSION_COOKIE"])
    if token:
        db.execute(
            "UPDATE sessions SET secret_unlocked = ? WHERE token_hash = ? AND user_id = ?",
            (value, hash_token(token), user_id),
        )
    else:
        db.execute("UPDATE sessions SET secret_unlocked = ? WHERE user_id = ?", (value, user_id))


def _group_payload(db, group, user_id: int) -> dict:
    unlocked = _secret_unlocked(db, user_id) if group["kind"] == "secret" else True
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
        "count": count,
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
        SELECT g.*, (
            SELECT COUNT(*) FROM bookmarks b
            WHERE b.group_id = g.id AND b.user_id = g.user_id AND b.deleted_at IS NULL
        ) AS count
        FROM groups g WHERE g.user_id = ?
        ORDER BY
            CASE g.kind WHEN 'favorites' THEN 0 WHEN 'secret' THEN 1 ELSE 2 END,
            g.position, g.id
        """,
        (uid,),
    ).fetchall()
    return jsonify({"groups": [_group_payload(db, row, uid) for row in rows]})


@bp.post("/groups")
def create_group():
    data = _json()
    name = clean_text(data.get("name"), 40)
    icon = clean_text(data.get("icon"), 8) or "📁"
    if not name:
        return _error("group_name_required")
    db = _db()
    uid = _uid()
    total = db.execute("SELECT COUNT(*) c FROM groups WHERE user_id = ?", (uid,)).fetchone()["c"]
    if total >= 80:
        return _error("too_many_groups")
    position = db.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 p FROM groups WHERE user_id = ?", (uid,)
    ).fetchone()["p"]
    cursor = db.execute(
        "INSERT INTO groups(user_id, name, icon, kind, position, created_at)"
        " VALUES (?, ?, ?, 'custom', ?, ?)",
        (uid, name, icon, position, iso()),
    )
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

    Non-empty password (min 4 chars) sets a new one and locks the group
    again; an empty one removes the password (the group becomes open).
    """
    uid = _uid()
    if "password" not in data:
        return _error("secret_locked")
    password = data.get("password")
    password = password.strip() if isinstance(password, str) else ""
    if password:
        if len(password) < 4:
            return _error("secret_password_short")
        if len(password) > 200:
            return _error("password_too_long")
        db.execute(
            "UPDATE groups SET password_hash = ? WHERE id = ? AND user_id = ?",
            (hash_password(password), group["id"], uid),
        )
        _set_secret_unlocked(db, uid, 0)
    else:
        db.execute(
            "UPDATE groups SET password_hash = NULL WHERE id = ? AND user_id = ?",
            (group["id"], uid),
        )
        _set_secret_unlocked(db, uid, 1)
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
    db.execute("UPDATE groups SET name = ?, icon = ? WHERE id = ?", (name, icon or "📁", group_id))
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
    password = _json().get("password")
    if not isinstance(password, str) or not password:
        return _error("password_required")
    if not verify_password(password, group["password_hash"]):
        return _error("wrong_password")
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

    sql = BOOKMARK_SELECT + " WHERE b.user_id = ?"
    params: list[object] = [uid]
    sql += " AND b.deleted_at IS NOT NULL" if trash else " AND b.deleted_at IS NULL"

    secret_ids = [
        row["id"]
        for row in db.execute(
            "SELECT id FROM groups WHERE user_id = ? AND kind = 'secret'", (uid,)
        ).fetchall()
    ]

    if favorites:
        sql += " AND g.kind = 'favorites'"
    elif group_id not in (None, "", "0"):
        group = _get_group(db, uid, group_id)
        if group is None:
            return _error("not_found", 404)
        if group["kind"] == "secret" and not _secret_unlocked(db, uid):
            # Locked: the links stay invisible to this session.
            return jsonify({"bookmarks": [], "total": 0})
        sql += " AND b.group_id = ?"
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
            sql += f" AND (b.group_id IS NULL OR b.group_id NOT IN ({placeholders}))"
            params.extend(secret_ids)

    if tag:
        sql += (
            " AND EXISTS (SELECT 1 FROM bookmark_tags bt JOIN tags t ON t.id = bt.tag_id"
            " WHERE bt.bookmark_id = b.id AND t.name = ? COLLATE NOCASE)"
        )
        params.append(tag)

    if query:
        tokens = [token for token in query.split() if token][:6]
        for token in tokens:
            pattern = like_pattern(token)
            sql += (
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
    sql += f" ORDER BY {pinned_sql}{order} {direction_sql}, b.id {direction_sql}"

    rows = db.execute(sql, params).fetchall()
    tags = _tags_for(db, [row["id"] for row in rows])
    return jsonify(
        {
            "bookmarks": [_bookmark_dict(row, tags.get(row["id"], [])) for row in rows],
            "total": len(rows),
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
    if not data.get("allow_duplicate"):
        duplicate = db.execute(
            """
            SELECT b.id, b.title, g.name AS group_name
            FROM bookmarks b LEFT JOIN groups g ON g.id = b.group_id
            WHERE b.user_id = ? AND b.url = ? AND b.deleted_at IS NULL
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
        fields["group_id"] = group["id"] if group else None
        if group is not None and group["kind"] == "favorites":
            fields["favorite"] = 1
    if "tags" in data:
        _set_tags(db, uid, bookmark_id, parse_tags(data.get("tags")))
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
    row = _fetch_bookmark(db, _uid(), bookmark_id)
    if row is None:
        return _error("not_found", 404)
    db.execute("DELETE FROM bookmarks WHERE id = ? AND user_id = ?", (bookmark_id, _uid()))
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


@bp.post("/trash/empty")
def empty_trash():
    db = _db()
    rows = db.execute(
        "SELECT COUNT(*) c FROM bookmarks WHERE user_id = ? AND deleted_at IS NOT NULL", (_uid(),)
    ).fetchone()
    db.execute("DELETE FROM bookmarks WHERE user_id = ? AND deleted_at IS NOT NULL", (_uid(),))
    db.commit()
    return jsonify({"ok": True, "deleted": rows["c"]})


@bp.post("/trash/restore-all")
def restore_all():
    db = _db()
    rows = db.execute(
        "SELECT COUNT(*) c FROM bookmarks WHERE user_id = ? AND deleted_at IS NOT NULL", (_uid(),)
    ).fetchone()
    db.execute(
        "UPDATE bookmarks SET deleted_at = NULL WHERE user_id = ? AND deleted_at IS NOT NULL",
        (_uid(),),
    )
    db.commit()
    return jsonify({"ok": True, "restored": rows["c"]})


# ---------------------------------------------------------------------------
# Tags & statistics
# ---------------------------------------------------------------------------


@bp.get("/tags")
def list_tags():
    db = _db()
    rows = db.execute(
        """
        SELECT t.id, t.name, COUNT(b.id) AS count
        FROM tags t
        JOIN bookmark_tags bt ON bt.tag_id = t.id
        JOIN bookmarks b ON b.id = bt.bookmark_id AND b.deleted_at IS NULL
        WHERE t.user_id = ?
        GROUP BY t.id, t.name
        HAVING COUNT(b.id) > 0
        ORDER BY count DESC, t.name COLLATE NOCASE
        """,
        (_uid(),),
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
    row = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM bookmarks WHERE user_id = ? AND deleted_at IS NULL) AS bookmarks,
            (SELECT COUNT(*) FROM bookmarks WHERE user_id = ? AND deleted_at IS NOT NULL) AS trash,
            (SELECT COUNT(*) FROM groups WHERE user_id = ? AND kind = 'custom') AS groups,
            (SELECT COUNT(DISTINCT t.id) FROM tags t
                JOIN bookmark_tags bt ON bt.tag_id = t.id
                JOIN bookmarks b ON b.id = bt.bookmark_id AND b.deleted_at IS NULL
                WHERE t.user_id = ?) AS tags,
            (SELECT COALESCE(SUM(visits), 0) FROM bookmarks WHERE user_id = ? AND deleted_at IS NULL) AS visits,
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
            return send_file(data_path, mimetype=meta.get("mime") or "image/png", max_age=604800)
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
    group_names = {row["id"]: row["name"] for row in group_rows}
    rows = db.execute(
        BOOKMARK_SELECT
        + " WHERE b.user_id = ? AND b.deleted_at IS NULL"
        + " ORDER BY b.created_at ASC, b.id ASC",
        (uid,),
    ).fetchall()
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
        for group in group_rows:
            name = "Favorites" if group["kind"] == "favorites" else group["name"]
            lines.append(f"    <DT><H3>{_xml_escape(name)}</H3>")
            lines.append("    <DL><p>")
            for row in rows:
                if row["group_id"] != group["id"]:
                    continue
                tags_attr = ",".join(tags.get(row["id"], []))
                created = parse_iso(row["created_at"])
                add_date = int(created.timestamp()) if created else int(time.time())
                lines.append(
                    f'        <DT><A HREF="{_xml_escape(row["url"])}"'
                    f' ADD_DATE="{add_date}"'
                    f' TAGS="{_xml_escape(tags_attr)}">{_xml_escape(row["title"])}</A>'
                )
                if row["description"]:
                    lines.append(f"        <DD>{_xml_escape(row['description'])}")
            lines.append("    </DL><p>")
        lines.append("</DL><p>")
        payload = "\n".join(lines).encode("utf-8")
        return send_file(
            io.BytesIO(payload),
            mimetype="text/html; charset=utf-8",
            as_attachment=True,
            download_name=f"bookmarks-{stamp}.html",
        )

    payload = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "exported_at": iso(),
        "groups": [
            {"name": "Favorites" if row["kind"] == "favorites" else row["name"], "icon": row["icon"], "kind": row["kind"]}
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
                "icon": row["icon"],
                "created_at": row["created_at"],
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
        return folders, items
    raw = json.loads(content)
    if isinstance(raw, list):
        return [], raw
    if not isinstance(raw, dict):
        raise ValueError("Unsupported JSON structure")
    items = raw.get("bookmarks")
    if not isinstance(items, list):
        raise ValueError("No bookmarks found in file")
    groups = raw.get("groups") if isinstance(raw.get("groups"), list) else []
    return groups, items


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
        group_specs, items = _parse_import(fmt, content)
    except (ValueError, json.JSONDecodeError):
        return _error("invalid_file")

    db = _db()
    uid = _uid()
    existing = {
        row["url"]
        for row in db.execute(
            "SELECT url FROM bookmarks WHERE user_id = ? AND deleted_at IS NULL", (uid,)
        ).fetchall()
    }
    groups = {
        row["name"].casefold(): row
        for row in db.execute("SELECT * FROM groups WHERE user_id = ?", (uid,)).fetchall()
    }
    favorites = _favorites_group(db, uid)
    groups.setdefault("favorites", favorites)
    position = db.execute(
        "SELECT COALESCE(MAX(position), 0) AS p FROM groups WHERE user_id = ?", (uid,)
    ).fetchone()["p"]
    created_groups = 0
    for spec in group_specs:
        if not isinstance(spec, dict):
            continue
        name = clean_text(spec.get("name"), 40)
        if not name:
            continue
        key = name.casefold()
        if key in groups:
            continue
        if spec.get("kind") == "favorites":
            groups[key] = favorites
            continue
        if created_groups >= 80:
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
    for item in items[:5000]:
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
        group_name = item.get("group") or item.get("folder") or ""
        group = groups.get(str(group_name).casefold()) if group_name else None
        if group is None and item.get("favorite"):
            group = favorites
        title = clean_text(item.get("title"), 300) or guess_title(url)
        description = clean_text(item.get("description"), 2000, multiline=True)
        tags = parse_tags(item.get("tags"))
        icon_uri = validate_image_data_uri(item.get("icon"))
        cursor = db.execute(
            "INSERT INTO bookmarks(user_id, group_id, url, title, description, favorite, pinned,"
            " visits, created_at, updated_at, icon) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
            (
                uid,
                group["id"] if group else None,
                url,
                title,
                description,
                1 if group is not None and group["kind"] == "favorites" else 0,
                int(item.get("visits") or 0) if isinstance(item.get("visits"), (int, float)) else 0,
                item.get("created_at") if isinstance(item.get("created_at"), str) else now,
                now,
                icon_uri,
            ),
        )
        _set_tags(db, uid, int(cursor.lastrowid), tags)
        existing.add(url)
        imported += 1
    db.commit()
    return jsonify(
        {"ok": True, "imported": imported, "skipped": skipped, "groups_created": created_groups}
    )

