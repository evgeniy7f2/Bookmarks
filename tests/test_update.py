# -*- coding: utf-8 -*-
"""v1.4.0 regression tests: auto-update API endpoints and the installer package."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import update as updater  # noqa: E402
from bookmarks import api as api_module  # noqa: E402
from bookmarks.util import APP_VERSION  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _register(client, username, password="secret123"):
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["user"]


@pytest.fixture()
def admin_client(client):
    """The first registered user becomes the admin."""
    body = _register(client, "boss")
    assert body["is_admin"] is True
    return client


@pytest.fixture()
def plain_client(client):
    """A non-admin client (registered after the admin)."""
    _register(client, "boss")
    body = _register(client, "worker")
    assert body["is_admin"] is False
    return client


# ---------------------------------------------------------------------------
# /api/update/check
# ---------------------------------------------------------------------------


def test_update_check_reports_new_version(admin_client, monkeypatch):
    monkeypatch.setattr(
        updater, "fetch_latest", lambda: {"version": "99.0.0", "url": "u", "source": "release"}
    )
    response = admin_client.get("/api/update/check")
    assert response.status_code == 200
    body = response.get_json()
    assert body["current"] == APP_VERSION
    assert body["latest"] == "99.0.0"
    assert body["available"] is True
    assert body["source"] == "release"


def test_update_check_up_to_date(admin_client, monkeypatch):
    monkeypatch.setattr(
        updater, "fetch_latest", lambda: {"version": "0.0.1", "url": "u", "source": "branch"}
    )
    response = admin_client.get("/api/update/check")
    assert response.status_code == 200
    body = response.get_json()
    assert body["available"] is False
    assert body["current"] == APP_VERSION


def test_update_check_github_unreachable(admin_client, monkeypatch):
    monkeypatch.setattr(updater, "fetch_latest", lambda: None)
    response = admin_client.get("/api/update/check")
    assert response.status_code == 502
    assert response.get_json()["error"] == "github_unreachable"


def test_update_check_forbidden_for_non_admin(plain_client, monkeypatch):
    monkeypatch.setattr(
        updater, "fetch_latest", lambda: {"version": "99.0.0", "url": "u", "source": "release"}
    )
    response = plain_client.get("/api/update/check")
    assert response.status_code == 403
    assert response.get_json()["error"] == "forbidden"


def test_update_check_requires_login(client):
    response = client.get("/api/update/check")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# /api/update/run
# ---------------------------------------------------------------------------


class FakeProc:
    pid = 4242

    def __init__(self, *args, **kwargs):  # noqa: ARG002 - mimic Popen signature
        self.cmd = args[0] if args else None


def test_update_run_starts_updater_and_writes_pid(admin_client, app, monkeypatch):
    started = []

    def fake_popen(cmd, **kwargs):
        started.append(cmd)
        return FakeProc()

    monkeypatch.setattr(api_module.subprocess, "Popen", fake_popen)
    response = admin_client.post("/api/update/run")
    assert response.status_code == 200
    body = response.get_json()
    assert body["started"] is True
    assert body["pid"] == FakeProc.pid
    assert "update.py" in " ".join(started[0])
    pid_file = Path(app.config["DATA_DIR"]) / "update.pid"
    assert pid_file.read_text(encoding="utf-8").strip() == str(FakeProc.pid)


def test_update_run_already_running(admin_client, app, monkeypatch):
    pid_file = Path(app.config["DATA_DIR"]) / "update.pid"
    pid_file.write_text("31337", encoding="utf-8")
    monkeypatch.setattr(api_module, "_pid_alive", lambda _pid: True)
    response = admin_client.post("/api/update/run")
    assert response.status_code == 409
    assert response.get_json()["error"] == "already_running"


def test_update_run_forbidden_for_non_admin(plain_client):
    response = plain_client.post("/api/update/run")
    assert response.status_code == 403


def test_update_run_missing_update_py(admin_client, monkeypatch):
    real_exists = os.path.exists

    def fake_exists(path):
        return False if str(path).endswith("update.py") else real_exists(path)

    monkeypatch.setattr(os.path, "exists", fake_exists)
    response = admin_client.post("/api/update/run")
    assert response.status_code == 500
    assert response.get_json()["error"] == "updater_missing"


# ---------------------------------------------------------------------------
# update.py logic (no network)
# ---------------------------------------------------------------------------


def test_update_py_parse_version():
    assert updater.parse_version("1.4.0") == (1, 4, 0)
    assert updater.parse_version("v1.4.0") == (1, 4, 0)
    assert updater.parse_version("  12.3.4 ") == (12, 3, 4)
    # a two-part string is not a full version
    assert updater.parse_version("12.3") is None
    assert updater.parse_version("nope") is None
    assert updater.parse_version("") is None


def test_update_py_pick_best_highest_version_wins():
    candidates = [
        {"version": "1.4.0", "source": "branch"},
        {"version": "1.0.9", "source": "release"},
    ]
    assert updater._pick_best(candidates, None)["version"] == "1.4.0"
    candidates = [
        {"version": "1.0.9", "source": "release"},
        {"version": "1.4.0", "source": "branch"},
    ]
    assert updater._pick_best(candidates, None)["version"] == "1.4.0"


def test_update_py_current_version_reads_util():
    assert updater.current_version() == APP_VERSION


# ---------------------------------------------------------------------------
# installer package: i18n parity + core helpers
# ---------------------------------------------------------------------------


def _installer_strings():
    from installer import i18n

    return i18n.STRINGS


def test_installer_i18n_ru_en_parity():
    strings = _installer_strings()
    ru, en = strings["ru"], strings["en"]
    assert ru and en
    assert not (set(ru) - set(en)), f"missing in EN: {sorted(set(ru) - set(en))}"
    assert not (set(en) - set(ru)), f"missing in RU: {sorted(set(en) - set(ru))}"


def test_installer_i18n_placeholders_match():
    """RU and EN values for the same key must use the same {placeholders}."""

    def fields(text: str) -> set[str]:
        return set(re.findall(r"\{([a-zA-Z0-9_]+)\}", text))

    strings = _installer_strings()
    mismatches = {
        key: (fields(strings["ru"][key]), fields(strings["en"][key]))
        for key in strings["ru"]
        if fields(strings["ru"][key]) != fields(strings["en"][key])
    }
    assert not mismatches, f"placeholder mismatch: {mismatches}"


def test_installer_i18n_t_falls_back_to_key():
    from installer import i18n

    assert i18n.t("ru", "no.such.key") == "no.such.key"
    assert i18n.t("xx", "app.title") == i18n.STRINGS["ru"]["app.title"]
    text = i18n.t("ru", "step.update.uptodate", ver="1.2.3")
    assert "1.2.3" in text


def test_core_parse_version():
    from installer.core import parse_version

    assert parse_version("1.4.0") == (1, 4, 0)
    assert parse_version("v2.0.0") == (2, 0, 0)
    assert parse_version("1.2") is None
    assert parse_version("garbage") is None


def test_core_validate_ip():
    from installer.core import InstallError, validate_ip

    assert validate_ip("192.168.100.20") == "192.168.100.20"
    assert validate_ip("my-server.local") == "my-server.local"
    for bad in ("", "256.1.1.1", "a..b", "1.2.3", "has space"):
        with pytest.raises(InstallError):
            validate_ip(bad)


def test_core_validate_port():
    from installer.core import InstallError, validate_port

    assert validate_port("8765") == 8765
    assert validate_port("1") == 1
    for bad in ("", "0", "65536", "port", "-5"):
        with pytest.raises(InstallError):
            validate_port(bad)


def test_core_app_version_from_dir(tmp_path):
    from installer.core import app_version_from_dir

    util = tmp_path / "bookmarks" / "util.py"
    util.parent.mkdir(parents=True)
    util.write_text('APP_VERSION = "7.7.7"\n', encoding="utf-8")
    assert app_version_from_dir(tmp_path) == "7.7.7"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert app_version_from_dir(empty) == "0.0.0"


def test_installer_modules_import_cleanly():
    """All installer modules must import without third-party dependencies."""
    import importlib

    for name in ("installer", "installer.core", "installer.i18n",
                 "installer.remote", "installer.win", "installer.actions"):
        module = importlib.import_module(name)
        assert module is not None


def test_method_cards_have_i18n_keys():
    """Regression: the method screen formats f"method.{key}.*" — the Windows
    method is stored as "windows" but the i18n keys use "win"."""
    pytest.importorskip("tkinter")
    from installer import i18n, installer as inst

    for method in inst.METHODS:
        key = "win" if method == "windows" else method
        for suffix in ("title", "desc"):
            full = f"method.{key}.{suffix}"
            assert full in i18n.STRINGS["ru"], f"{full} missing in RU"
            assert full in i18n.STRINGS["en"], f"{full} missing in EN"


# ---------------------------------------------------------------------------
# frontend guards (the About dialog's update section)
# ---------------------------------------------------------------------------

APP_JS = ROOT / "bookmarks" / "static" / "js" / "app.js"
WEB_I18N = ROOT / "bookmarks" / "static" / "js" / "i18n.js"


def test_about_dialog_wires_update_endpoints():
    text = APP_JS.read_text(encoding="utf-8")
    assert "mountUpdateSection" in text
    assert '"/update/check"' in text
    assert '"/update/run"' in text
    assert "window.location.reload()" in text
    assert "isAdmin ? { onMount" in text


def test_web_i18n_has_update_keys():
    text = WEB_I18N.read_text(encoding="utf-8")
    for key in (
        "about.updates",
        "about.update.idle",
        "about.update.check",
        "about.update.run",
        "about.update.checking",
        "about.update.available",
        "about.update.uptodate",
        "about.update.error",
        "about.update.confirm",
        "about.update.running",
        "about.update.timeout",
    ):
        # each key must appear in both the RU and EN blocks
        count = text.count(f'"{key}"')
        assert count == 2, f"{key} expected in RU and EN, found {count} times"
