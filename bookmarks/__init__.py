"""Application factory for Bookmarks."""

from __future__ import annotations

import os
import secrets

from flask import Flask, abort, g, jsonify, redirect, render_template, request
from werkzeug.exceptions import HTTPException

from . import admin, api, auth, db
from .util import APP_NAME, APP_VERSION, iso

INDEX_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "manifest-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def _load_secret(data_dir: str) -> str:
    env_secret = os.environ.get("BOOKMARKS_SECRET")
    if env_secret:
        return env_secret
    path = os.path.join(data_dir, "secret.key")
    os.makedirs(data_dir, exist_ok=True)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
        if value:
            return value
    value = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(value)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return value


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.environ.get("BOOKMARKS_DATA") or os.path.join(project_root, "data")

    app.config.update(
        DATA_DIR=data_dir,
        DATABASE=os.path.join(data_dir, "bookmarks.db"),
        ICON_DIR=os.path.join(data_dir, "icons"),
        SESSION_COOKIE="bms_session",
        SESSION_REMEMBER_DAYS=30,
        SESSION_COOKIE_SECURE=os.environ.get("BOOKMARKS_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"},
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)
        if "DATABASE" in test_config:
            app.config["DATA_DIR"] = os.path.dirname(test_config["DATABASE"])
        if "DATA_DIR" in test_config:
            app.config["ICON_DIR"] = os.path.join(test_config["DATA_DIR"], "icons")

    os.makedirs(app.config["DATA_DIR"], exist_ok=True)
    os.makedirs(app.config["ICON_DIR"], exist_ok=True)
    app.secret_key = _load_secret(app.config["DATA_DIR"])
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    if os.environ.get("BOOKMARKS_TRUST_PROXY", "").strip().lower() in {"1", "true", "yes"}:
        # Behind nginx/Caddy: trust one hop of X-Forwarded-* headers so that
        # rate limits and redirects see the real client address and scheme.
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(admin.bp)

    @app.before_request
    def check_origin():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("Origin")
            if origin and origin != "null":
                from urllib.parse import urlsplit

                if urlsplit(origin).netloc != request.host:
                    abort(403)
            elif request.headers.get("Sec-Fetch-Site") == "cross-site":
                # No Origin header, but the browser says the request came
                # from another site (CSRF). Non-browser clients (curl, the
                # test suite) send neither header and are allowed through.
                abort(403)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        if request.path == "/" or request.path.startswith("/api/"):
            response.headers.setdefault("Content-Security-Policy", INDEX_CSP)
        if request.path == "/":
            response.headers["Cache-Control"] = "no-store"
        elif request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=3600")
        return response

    @app.get("/")
    def index():
        return render_template("index.html", version=APP_VERSION)

    @app.get("/health")
    def health():
        # A broken database must be visible to the Docker healthcheck.
        try:
            db.get_db().execute("SELECT 1").fetchone()
            database_ok = True
        except Exception:  # noqa: BLE001 - reported in the payload, not raised
            database_ok = False
        return (
            jsonify(
                {
                    "app": APP_NAME,
                    "version": APP_VERSION,
                    "schema": db.SCHEMA_VERSION,
                    "db": database_ok,
                    "ok": database_ok,
                }
            ),
            200 if database_ok else 503,
        )

    @app.get("/go/<int:bookmark_id>")
    def open_bookmark(bookmark_id: int):
        if g.get("user") is None:
            return redirect("/")
        connection = db.get_db()
        row = connection.execute(
            "SELECT b.url, g.kind AS group_kind"
            " FROM bookmarks b LEFT JOIN groups g ON g.id = b.group_id"
            " WHERE b.id = ? AND b.user_id = ? AND b.deleted_at IS NULL",
            (bookmark_id, g.user["id"]),
        ).fetchone()
        if row is None:
            abort(404)
        if row["group_kind"] == "secret" and api.secret_locked(connection, g.user["id"]):
            # A closed Secret group is indistinguishable from a missing link.
            abort(404)
        url = row["url"]
        from urllib.parse import urlsplit

        if urlsplit(url).scheme not in ("http", "https"):
            abort(404)
        connection.execute(
            "UPDATE bookmarks SET visits = visits + 1, last_visit_at = ? WHERE id = ?",
            (iso(), bookmark_id),
        )
        connection.commit()
        return redirect(url, code=302)

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": error.name.lower().replace(" ", "_")}), error.code
        return error

    return app
