# -*- coding: utf-8 -*-
"""v1.4.0 regression tests: the self-contained installer bootstrapper
(installer_bootstrap.py → bookmarks_install_v140.exe)."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import installer_bootstrap as b  # noqa: E402


# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------


def test_constants():
    assert b.REPO == "evgeniy7f2/Bookmarks"
    assert b.ASSET_NAME == "GITHUB_Files.zip"
    assert b.BOOTSTRAP_VERSION == "1.4.0"
    assert b.BRANCH_ZIP == (
        "https://github.com/evgeniy7f2/Bookmarks/archive/refs/heads/main.zip"
    )
    assert b.API.endswith("/repos/evgeniy7f2/Bookmarks")


# ---------------------------------------------------------------------------
# extract_payload (flat release-asset zip and wrapped GitHub zipball)
# ---------------------------------------------------------------------------


def _make_zip(path: Path, wrapped: bool, with_installer: bool = True) -> None:
    prefix = Path("Bookmarks-main") if wrapped else Path(".")
    with zipfile.ZipFile(path, "w") as z:
        if with_installer:
            z.writestr(str(prefix / "installer" / "__init__.py"), "")
            z.writestr(str(prefix / "installer" / "core.py"), "X = 1\n")
        z.writestr(str(prefix / "app.py"), "print('app')\n")
        z.writestr(str(prefix / "bookmarks" / "__init__.py"), "")


def test_extract_payload_flat(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "PAYLOAD_DIR", tmp_path / "payload")
    z = tmp_path / "flat.zip"
    _make_zip(z, wrapped=False)
    got = b.extract_payload(z)
    assert got == tmp_path / "payload"
    assert (got / "installer" / "core.py").is_file()
    assert (got / "app.py").is_file()


def test_extract_payload_wrapped_zipball(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "PAYLOAD_DIR", tmp_path / "payload")
    z = tmp_path / "wrapped.zip"
    _make_zip(z, wrapped=True)
    got = b.extract_payload(z)
    assert got == tmp_path / "payload"
    # the wrapper folder must not remain in the payload root
    assert (got / "Bookmarks-main").is_dir() is False
    assert (got / "installer" / "__init__.py").is_file()


def test_extract_payload_without_installer(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "PAYLOAD_DIR", tmp_path / "payload")
    z = tmp_path / "plain.zip"
    _make_zip(z, wrapped=False, with_installer=False)
    assert b.extract_payload(z) is None


def test_extract_payload_replaces_previous(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "PAYLOAD_DIR", tmp_path / "payload")
    z1, z2 = tmp_path / "a.zip", tmp_path / "b.zip"
    _make_zip(z1, wrapped=False)
    _make_zip(z2, wrapped=False)
    b.extract_payload(z1)
    got = b.extract_payload(z2)
    assert got == tmp_path / "payload"
    assert (got / "installer" / "__init__.py").is_file()


# ---------------------------------------------------------------------------
# embedded payload / flags
# ---------------------------------------------------------------------------


def test_embedded_payload_dir_not_frozen(monkeypatch):
    monkeypatch.setattr(b, "FROZEN", False)
    assert b.embedded_payload_dir() is None


def test_flag_value():
    assert b._flag_value(["--offline", "D:\\x"], "--offline") == "D:\\x"
    assert b._flag_value(["--offline"], "--offline") is None  # no value
    assert b._flag_value([], "--offline") is None
    assert b._flag_value(["--download", "u"], "--other") is None


# ---------------------------------------------------------------------------
# GitHub source resolution
# ---------------------------------------------------------------------------


def test_resolve_download_url_prefers_release_asset(monkeypatch):
    info = {
        "tag_name": "v1.4.0",
        "assets": [
            {"name": "other.zip", "browser_download_url": "https://x/other.zip"},
            {"name": "GITHUB_Files.zip", "browser_download_url": "https://x/files.zip"},
        ],
    }
    monkeypatch.setattr(b, "http_json", lambda url, timeout=20: info)
    url, label = b.resolve_download_url()
    assert url == "https://x/files.zip"
    assert "v1.4.0" in label


def test_resolve_download_url_falls_back_to_branch(monkeypatch):
    def boom(url, timeout=20):
        raise OSError("no network")

    monkeypatch.setattr(b, "http_json", boom)
    url, label = b.resolve_download_url()
    assert url == b.BRANCH_ZIP
    assert label == "main branch"


# ---------------------------------------------------------------------------
# download() with a fake HTTP response
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, data: bytes):
        self._buf = data
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        chunk = self._buf[:n]
        self._buf = self._buf[n:]
        return chunk


def test_download_streams_and_reports_progress(monkeypatch, tmp_path):
    data = b"0123456789" * 3000  # 30 KB, several chunks
    monkeypatch.setattr(
        b.urllib.request, "urlopen", lambda req, timeout=0: _FakeResp(data)
    )
    got_calls = []
    dest = tmp_path / "sub" / "out.zip"
    b.download("https://example/x.zip", dest, lambda g, t: got_calls.append((g, t)))
    assert dest.read_bytes() == data
    assert got_calls, "progress callback never called"
    assert got_calls[-1] == (len(data), len(data))
