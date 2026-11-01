"""SQLite storage: schema, connections and tiny helpers."""

from __future__ import annotations

import os
import sqlite3

from flask import current_app, g

SCHEMA_VERSION = "6"

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL COLLATE NOCASE UNIQUE,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    avatar_color  TEXT NOT NULL DEFAULT '#6366f1',
    settings      TEXT NOT NULL DEFAULT '{}',
    disabled      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ip         TEXT,
    user_agent TEXT,
    secret_unlocked INTEGER NOT NULL DEFAULT 0,
    secret_unlocked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    icon       TEXT NOT NULL DEFAULT '📁',
    kind       TEXT NOT NULL DEFAULT 'custom',
    position   INTEGER NOT NULL DEFAULT 0,
    password_hash TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_groups_user ON groups(user_id);

CREATE TABLE IF NOT EXISTS bookmarks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id      INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    favorite      INTEGER NOT NULL DEFAULT 0,
    origin_id     INTEGER,
    pinned        INTEGER NOT NULL DEFAULT 0,
    visits        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    last_visit_at TEXT,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(user_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_bookmarks_group ON bookmarks(group_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_origin ON bookmarks(origin_id);

CREATE TABLE IF NOT EXISTS tags (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name    TEXT NOT NULL COLLATE NOCASE,
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS bookmark_tags (
    bookmark_id INTEGER NOT NULL REFERENCES bookmarks(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (bookmark_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_bookmark_tags_tag ON bookmark_tags(tag_id);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _migrate_unique_group_names(connection: sqlite3.Connection) -> None:
    """One group name per user (case-insensitive) plus a unique index.

    Duplicates already present in the database (manual creation or an
    import that merged by name) get a " (2)"-style suffix so the unique
    index can be created. Runs once; afterwards the index exists.
    """
    if any(
        row["name"] == "idx_groups_user_name"
        for row in connection.execute("PRAGMA index_list(groups)")
    ):
        return
    rows = connection.execute(
        "SELECT id, user_id, name FROM groups ORDER BY user_id, id"
    ).fetchall()
    claimed: dict[tuple[int, str], int] = {}
    first_seen: dict[tuple[int, str], str] = {}

    def free_name(user_id: int, base: str) -> str:
        number = 1
        candidate = base
        while (user_id, candidate.casefold()) in claimed:
            number += 1
            candidate = f"{base} ({number})"
        return candidate

    for row in rows:
        case_key = row["name"].casefold()
        if (row["user_id"], case_key) in claimed:
            # Suffix the first occurrence's spelling: "Work", "Work (2)".
            base = first_seen.get((row["user_id"], case_key), row["name"])
            new_name = free_name(row["user_id"], base)
            connection.execute("UPDATE groups SET name = ? WHERE id = ?", (new_name, row["id"]))
            case_key = new_name.casefold()
        else:
            first_seen[(row["user_id"], case_key)] = row["name"]
        claimed[(row["user_id"], case_key)] = 1
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_user_name"
        " ON groups(user_id, name COLLATE NOCASE)"
    )


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def prune_icon_cache(directory: str, max_files: int = 2000) -> None:
    """Drop the oldest cached favicons once the cache outgrows *max_files*.

    The cache is content-addressed (sha256 of the origin), so a removed entry
    is simply re-fetched the next time the site is opened.
    """
    try:
        entries: list[tuple[float, str]] = []
        for name in os.listdir(directory):
            if not name.endswith(".bin"):
                continue
            path = os.path.join(directory, name)
            try:
                entries.append((os.path.getmtime(path), name))
            except OSError:
                continue
        if len(entries) <= max_files:
            return
        entries.sort()
        for _mtime, name in entries[: len(entries) - max_files]:
            for suffix in (".bin", ".json"):
                try:
                    os.remove(os.path.join(directory, name[:-4] + suffix))
                except OSError:
                    pass
    except OSError:
        pass


def init_app(app) -> None:
    os.makedirs(app.config["DATA_DIR"], exist_ok=True)
    os.makedirs(app.config["ICON_DIR"], exist_ok=True)
    prune_icon_cache(app.config["ICON_DIR"])
    connection = connect(app.config["DATABASE"])
    try:
        connection.executescript(SCHEMA)
        for table, column, decl in (
            ("bookmarks", "icon", "TEXT"),
            ("users", "avatar_photo", "TEXT"),
            ("users", "disabled", "INTEGER NOT NULL DEFAULT 0"),
            ("groups", "password_hash", "TEXT"),
            ("sessions", "secret_unlocked", "INTEGER NOT NULL DEFAULT 0"),
            ("sessions", "secret_unlocked_at", "TEXT"),
            # v1.3.0: admin panel and per-user quotas.
            ("users", "is_admin", "INTEGER NOT NULL DEFAULT 0"),
            ("users", "max_bookmarks", "INTEGER"),
            ("users", "max_tags", "INTEGER"),
            ("users", "max_groups", "INTEGER"),
        ):
            existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        _migrate_unique_group_names(connection)
        connection.execute(
            "INSERT INTO app_meta(key, value) VALUES ('schema_version', ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SCHEMA_VERSION,),
        )
        # v1.0.9: every account gets the built-in Secret group (unless it
        # already has one). Favorites keeps working as before.
        connection.execute(
            """
            INSERT INTO groups(user_id, name, icon, kind, position, created_at)
            SELECT u.id, 'Secret', '🔐', 'secret', 0, ?
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM groups g WHERE g.user_id = u.id AND g.kind = 'secret'
            )
            """,
            (now_sql(),),
        )
        # v1.3.0: the very first account of an installation becomes the
        # admin, so the admin panel is reachable from day one without a
        # CLI. Later admins are granted from the panel itself.
        if (
            connection.execute("SELECT COUNT(*) c FROM users WHERE is_admin = 1")
            .fetchone()["c"]
            == 0
        ):
            first = connection.execute(
                "SELECT id FROM users ORDER BY id LIMIT 1"
            ).fetchone()
            if first:
                connection.execute(
                    "UPDATE users SET is_admin = 1 WHERE id = ?", (first["id"],)
                )
        # Housekeeping: sessions that already expired do not wait for a hit.
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now_sql(),))
        connection.commit()
    finally:
        connection.close()
    app.teardown_appcontext(close_db)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_error=None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def now_sql() -> str:
    from .util import iso

    return iso()
