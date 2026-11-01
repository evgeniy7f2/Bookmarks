# -*- coding: utf-8 -*-
"""Installer core: GitHub sources, validation, health checks.

The GUI (installer.py) calls the high-level functions with a log callback and
a cancel event; all user-visible text comes from i18n.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "evgeniy7f2/Bookmarks"
GITHUB_API = f"https://api.github.com/repos/{REPO}"
BRANCH_ZIP = f"https://github.com/{REPO}/archive/refs/heads/main.zip"
DEFAULT_PORT = 8765
HEALTH_TIMEOUT = 90
INSTALLER_DIR = Path(__file__).resolve().parent
EMBEDDED_PYTHON_VERSIONS = ["3.12.10", "3.12.9", "3.12.8", "3.12.7", "3.11.9"]
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# files/dirs never copied into the install directory
COPY_EXCLUDE_DIRS = {".venv", "data", "__pycache__", ".pytest_cache", ".git", "node_modules"}
COPY_EXCLUDE_FILES = {"GITHUB_Files.zip", "STATE.md", ".gitignore", ".dockerignore"}


class InstallError(Exception):
    """User-facing error: i18n key + formatting kwargs."""

    def __init__(self, key: str, **kwargs):
        self.key = key
        self.kwargs = kwargs
        super().__init__(key)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def parse_version(text: str):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def http_json(url: str, timeout: int = 15):
    req = urllib.request.Request(
        url, headers={"User-Agent": "BookmarksInstaller/1.0", "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_download(url: str, dest: Path, timeout: int = 300) -> Path:
    """Download url to dest (flat download, no progress callback needed)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)
    return dest


def validate_ip(value: str) -> str:
    value = value.strip()
    if not value:
        raise InstallError("err.ip")
    # allow dotted-quad or a hostname
    if re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", value):
        for part in value.split("."):
            if int(part) > 255:
                raise InstallError("err.ip")
        return value
    # digits and dots that are not a valid dotted quad (e.g. "1.2.3")
    if re.fullmatch(r"[\d.]+", value):
        raise InstallError("err.ip")
    if re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*", value):
        return value
    raise InstallError("err.ip")


def validate_port(value: str) -> int:
    value = value.strip()
    if not value.isdigit() or not (1 <= int(value) <= 65535):
        raise InstallError("err.port")
    return int(value)


def local_ip() -> str:
    """Best-guess local LAN address (UDP probe, no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def wait_health(ip: str, port: int, timeout: int = HEALTH_TIMEOUT, cancel=None, poll: float = 2.0):
    """Poll http://ip:port/health until it answers; returns the health dict or None."""
    import time

    deadline = time.time() + timeout
    url = f"http://{ip}:{port}/health"
    while time.time() < deadline:
        if cancel is not None and cancel.is_set():
            return None
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            time.sleep(poll)
    return None


def app_version_from_dir(source: Path) -> str:
    try:
        text = (Path(source) / "bookmarks" / "util.py").read_text(encoding="utf-8")
        m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
    except OSError:
        pass
    return "0.0.0"
