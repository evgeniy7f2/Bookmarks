#!/usr/bin/env python3
"""Administrative helpers for Bookmarks.

Commands:
  list-users                          show every account with usage stats
  reset-password <user> [new-password]  set a new password (random one is
                                        generated and printed if omitted)
  lock-user <user>                    block the account (existing sessions
                                      stop working, login is refused)
  unlock-user <user>                  unblock the account
  make-admin <user>                   grant admin rights (admin panel access)
  backup <file>                       consistent copy of the database
                                      (safe while the server is running)

Run from the project root:  python manage.py list-users
"""

from __future__ import annotations

import argparse
import os
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bookmarks.util import hash_password  # noqa: E402


def _data_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(os.path.abspath(explicit))
    env = os.environ.get("BOOKMARKS_DATA")
    if env:
        return Path(env)
    return ROOT / "data"


def _connect(data_dir: Path) -> sqlite3.Connection:
    database = data_dir / "bookmarks.db"
    if not database.exists():
        raise SystemExit(f"  БД не найдена: {database}")
    connection = sqlite3.connect(database, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def _find_user(db: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def _user_stats(db: sqlite3.Connection, user_id: int) -> tuple[int, int]:
    links = db.execute(
        "SELECT COUNT(*) c FROM bookmarks WHERE user_id = ? AND deleted_at IS NULL", (user_id,)
    ).fetchone()["c"]
    sessions = db.execute("SELECT COUNT(*) c FROM sessions WHERE user_id = ?", (user_id,)).fetchone()["c"]
    return links, sessions


def cmd_list_users(args) -> int:
    db = _connect(_data_dir(args.data))
    try:
        rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
        if not rows:
            print("  Аккаунтов пока нет.")
            return 0
        print(f"  {'ID':>4}  {'Имя':<20} {'Псевдоним':<18} {'Адм':<4} {'Закр':<6} {'Ссылки':>7} {'Сессий':>7}  Создан")
        print("  " + "-" * 84)
        for row in rows:
            links, sessions = _user_stats(db, row["id"])
            print(
                f"  {row['id']:>4}  {row['username']:<20} "
                f"{(row['display_name'] or '')[:18]:<18} "
                f"{('да' if row['is_admin'] else '—'):<4} "
                f"{('да' if row['disabled'] else '—'):<6} "
                f"{links:>7} {sessions:>7}  {row['created_at'][:10]}"
            )
    finally:
        db.close()
    return 0


def cmd_reset_password(args) -> int:
    db = _connect(_data_dir(args.data))
    try:
        row = _find_user(db, args.username)
        if row is None:
            print(f"  Пользователь не найден: {args.username}")
            return 1
        new_password = args.new_password or secrets.token_urlsafe(9)
        if len(new_password) < 8:
            print("  Новый пароль слишком короткий (минимум 8 символов).")
            return 1
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), row["id"]),
        )
        db.commit()
        print(f"  Пароль для {args.username} сброшен.")
        if not args.new_password:
            print(f"  Новый пароль: {new_password}")
    finally:
        db.close()
    return 0


def _set_disabled(args, value: int) -> int:
    db = _connect(_data_dir(args.data))
    try:
        row = _find_user(db, args.username)
        if row is None:
            print(f"  Пользователь не найден: {args.username}")
            return 1
        db.execute("UPDATE users SET disabled = ? WHERE id = ?", (value, row["id"]))
        db.commit()
        state = "заблокирован" if value else "разблокирован"
        print(f"  {args.username}: {state}.")
    finally:
        db.close()
    return 0


def cmd_make_admin(args) -> int:
    db = _connect(_data_dir(args.data))
    try:
        row = _find_user(db, args.username)
        if row is None:
            print(f"  Пользователь не найден: {args.username}")
            return 1
        if row["is_admin"]:
            print(f"  {args.username} уже администратор.")
            return 0
        db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (row["id"],))
        db.commit()
        print(f"  {args.username} — теперь администратор (админ-панель в интерфейсе).")
    finally:
        db.close()
    return 0


def cmd_lock_user(args) -> int:
    return _set_disabled(args, 1)


def cmd_unlock_user(args) -> int:
    return _set_disabled(args, 0)


def cmd_backup(args) -> int:
    """Copy the database with sqlite3's online backup API.

    Unlike a plain file copy this stays consistent with writers (WAL
    included), so it is safe to run while the server works.
    """
    source = _connect(_data_dir(args.data))
    target_path = Path(os.path.abspath(args.output))
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            target_path.unlink()
        destination = sqlite3.connect(target_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
        # Sanity check: the copy must be a readable SQLite file.
        check = sqlite3.connect(target_path)
        try:
            version = check.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            check.close()
        if version != "ok":
            print(f"  Внимание: integrity_check = {version}")
            return 1
    finally:
        source.close()
    size_kb = target_path.stat().st_size // 1024
    print(f"  Бэкап создан: {target_path} ({size_kb} КБ).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bookmarks — administrative helpers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Commands:", 1)[-1],
    )
    parser.add_argument("--data", help="data directory (default: $BOOKMARKS_DATA or ./data)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-users", help="show every account with usage stats")

    reset = sub.add_parser("reset-password", help="set a new password for an account")
    reset.add_argument("username")
    reset.add_argument("new_password", nargs="?", help="omit to generate a random one")

    lock = sub.add_parser("lock-user", help="block an account (instant logout, login refused)")
    lock.add_argument("username")

    unlock = sub.add_parser("unlock-user", help="unblock an account")
    unlock.add_argument("username")

    make_admin = sub.add_parser("make-admin", help="grant admin rights (admin panel)")
    make_admin.add_argument("username")

    backup = sub.add_parser("backup", help="consistent copy of the database (online)")
    backup.add_argument("output", help="where to write the copy")

    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    handlers = {
        "list-users": cmd_list_users,
        "reset-password": cmd_reset_password,
        "lock-user": cmd_lock_user,
        "unlock-user": cmd_unlock_user,
        "make-admin": cmd_make_admin,
        "backup": cmd_backup,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
