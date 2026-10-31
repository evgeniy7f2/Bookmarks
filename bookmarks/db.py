"""SQLite storage: schema, connections and tiny helpers."""

from __future__ import annotations

import os
import sqlite3

from flask import current_app, g

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
    secret_unlocked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

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


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def init_app(app) -> None:
    os.makedirs(app.config["DATA_DIR"], exist_ok=True)
    os.makedirs(app.config["ICON_DIR"], exist_ok=True)
    connection = connect(app.config["DATABASE"])
    try:
        connection.executescript(SCHEMA)
        for table, column, decl in (
            ("bookmarks", "icon", "TEXT"),
            ("users", "avatar_photo", "TEXT"),
            ("groups", "password_hash", "TEXT"),
            ("sessions", "secret_unlocked", "INTEGER NOT NULL DEFAULT 0"),
        ):
            existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        connection.execute(
            "INSERT OR IGNORE INTO app_meta(key, value) VALUES ('schema_version', '3')"
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
