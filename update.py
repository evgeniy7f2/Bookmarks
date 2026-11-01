#!/usr/bin/env python3
"""Bookmarks auto-updater (GitHub).

Usage:
  python update.py --check            only check for a new version
  python update.py --yes              update if a new version is available
  python update.py --force --yes      update unconditionally (reinstall files)
  python update.py --source <url> --yes
                                      install from a specific archive URL
                                      (a zip with the project files)

How it works:
  1. detects the environment: Windows / systemd / Docker / plain;
  2. finds the newest version on GitHub:
     - a release with a .zip asset (preferred), or a release tag archive;
     - otherwise the main branch archive (version read from bookmarks/util.py);
  3. downloads the archive, stops the server, replaces the files
     (data/ and .venv/ are preserved), updates the dependencies if
     requirements.txt changed, starts the server and waits for /health.

Only the Python standard library is used, so the updater can run inside the
app's virtual environment (which has just Flask + waitress).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = "evgeniy7f2/Bookmarks"
GITHUB_API = f"https://api.github.com/repos/{REPO}"
BRANCH_ZIP = f"https://github.com/{REPO}/archive/refs/heads/main.zip"
HEALTH_TIMEOUT = 90
EXCLUDE_DIRS = {".venv", "data", "__pycache__", ".pytest_cache", "node_modules"}
SKIP_FILES = {".gitignore", ".dockerignore"}


def log(msg: str) -> None:
    print(f"[update] {msg}", flush=True)


def parse_version(text: str):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def http_json(url: str, timeout: int = 15):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BookmarksUpdater/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_download(url: str, dest: Path, log_fn=log, timeout: int = 120) -> Path:
    """Download url to dest with a simple progress report."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                log_fn(f"\r[update] download {done // 1024} KB / {total // 1024} KB ({pct}%)")
        log_fn("")
    return dest


def current_version() -> str:
    try:
        text = (ROOT / "bookmarks" / "util.py").read_text(encoding="utf-8")
        m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
    except OSError:
        pass
    return "0.0.0"


def fetch_latest() -> dict | None:
    """Find the newest version on GitHub.

    Returns {"version", "url", "source", "zip_path"?, "tag"?} or None.
    """
    candidates: list[dict] = []

    # 1) latest release (asset zip, or the tag archive as fallback)
    try:
        data = http_json(f"{GITHUB_API}/releases/latest")
        tag = (data.get("tag_name") or "").strip()
        ver = parse_version(tag)
        if ver:
            assets = [a for a in data.get("assets", []) if a["name"].lower().endswith(".zip")]
            url = assets[0]["browser_download_url"] if assets else (
                f"https://github.com/{REPO}/archive/refs/tags/{urllib.request.quote(tag)}.zip"
            )
            candidates.append(
                {"version": ".".join(map(str, ver)), "url": url, "source": "release", "tag": tag}
            )
    except Exception as exc:
        log(f"release check: {exc.__class__.__name__} (fallback to the main branch)")

    # 2) main branch archive (version read from bookmarks/util.py)
    tmp = Path(tempfile.mkdtemp(prefix="bms-upd-"))
    try:
        zip_path = http_download(BRANCH_ZIP, tmp / "main.zip", log_fn=lambda *_: None)
        with zipfile.ZipFile(zip_path) as zf:
            names = [n for n in zf.namelist() if n.endswith("bookmarks/util.py")]
            if names:
                text = zf.read(names[0]).decode("utf-8", "replace")
                m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
                if m and parse_version(m.group(1)):
                    candidates.append(
                        {
                            "version": m.group(1),
                            "url": BRANCH_ZIP,
                            "source": "branch",
                            "zip_path": str(zip_path),
                        }
                    )
                    return _pick_best(candidates, keep_zip=str(zip_path))
    except Exception as exc:
        log(f"branch check: {exc.__class__.__name__}")
    finally:
        if not candidates or candidates[-1].get("zip_path") != str(tmp / "main.zip"):
            shutil.rmtree(tmp, ignore_errors=True)

    if not candidates:
        return None
    return _pick_best(candidates, keep_zip=None)


def _pick_best(candidates: list[dict], keep_zip: str | None) -> dict:
    # highest version wins; the branch candidate already carries its
    # downloaded zip (zip_path), the release candidate downloads it later.
    return max(candidates, key=lambda c: parse_version(c["version"]) or (0,))


def extract_zip(zip_path: Path) -> Path:
    """Extract the project archive; returns the directory containing app.py."""
    tmp = Path(tempfile.mkdtemp(prefix="bms-upd-"))
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp)
    candidates = [p for p in tmp.rglob("app.py")]
    if not candidates:
        raise SystemExit("[update] app.py not found inside the archive")
    return candidates[0].parent


def detect_env() -> str:
    if os.path.exists("/.dockerenv"):
        return "docker-inside"
    if os.name == "nt":
        return "windows"
    if (ROOT / "docker-compose.yml").exists() and _docker_container_running():
        return "docker"
    if Path("/etc/systemd/system/bookmarks.service").exists() or _systemd_unit_exists():
        return "systemd"
    return "plain"


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def _docker_container_running() -> bool:
    for compose in ("docker compose", "docker-compose"):
        try:
            parts = compose.split()
            proc = _run(parts + ["ps", "-q"], cwd=ROOT, timeout=30)
            if proc.returncode == 0 and proc.stdout.strip():
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def _systemd_unit_exists() -> bool:
    try:
        proc = _run(["systemctl", "cat", "bookmarks"], timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _port() -> int:
    try:
        info = json.loads((ROOT / "install.json").read_text(encoding="utf-8"))
        return int(info.get("port", 8765))
    except (OSError, ValueError, json.JSONDecodeError):
        return 8765


def _pid_by_port(port: int) -> int | None:
    try:
        proc = _run(["netstat", "-ano"], timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    wanted = f":{port} "
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(wanted.rstrip()) and parts[3] == "LISTENING":
            try:
                return int(parts[4])
            except ValueError:
                continue
    return None


def _venv_python(base: Path) -> str:
    if os.name == "nt":
        for cand in (base / ".venv" / "Scripts" / "python.exe", base / "python" / "python.exe"):
            if cand.exists():
                return str(cand)
    for cand in (base / ".venv" / "bin" / "python",):
        if cand.exists():
            return str(cand)
    return sys.executable


def stop_server(env: str) -> None:
    if env == "systemd":
        log("Stopping the systemd service (bookmarks) …")
        _run(["systemctl", "stop", "bookmarks"])
    elif env == "docker":
        log("Stopping the Docker container (docker compose stop) …")
        for compose in ("docker compose", "docker-compose"):
            try:
                proc = _run(compose.split() + ["stop"], cwd=ROOT, timeout=120)
                if proc.returncode == 0:
                    return
            except (OSError, subprocess.SubprocessError):
                continue
        log("docker compose stop failed — the container may already be stopped")
    elif env == "windows":
        port = _port()
        pid = _pid_by_port(port)
        if pid:
            log(f"Stopping the server (PID {pid}, port {port}) …")
            _run(["taskkill", "/F", "/PID", str(pid)])
        else:
            log(f"No process listening on port {port} — the server is not running")
    elif env == "plain":
        pid_file = ROOT / "data" / "server.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 15)
                log(f"Sent SIGTERM to PID {pid}")
            except (ValueError, OSError) as exc:
                log(f"Could not stop PID from server.pid: {exc}")
        else:
            log("No server.pid — please stop the server manually if it is running")
    else:
        log("Running inside a Docker container — the update must be started from the host")


def start_server(env: str) -> None:
    if env == "systemd":
        log("Starting the systemd service (bookmarks) …")
        _run(["systemctl", "start", "bookmarks"])
    elif env == "docker":
        log("Building the image and starting the container (docker compose up -d --build) …")
        for compose in ("docker compose", "docker-compose"):
            try:
                proc = _run(compose.split() + ["up", "-d", "--build"], cwd=ROOT, timeout=900)
                if proc.returncode == 0:
                    return
            except (OSError, subprocess.SubprocessError):
                continue
        log("docker compose up failed")
    elif env == "windows":
        port = _port()
        python = _venv_python(ROOT)
        data_dir = ROOT / "data"
        data_dir.mkdir(exist_ok=True)
        log(f"Starting the server: {python} app.py --port {port} …")
        with open(data_dir / "server.log", "ab") as log_file:
            subprocess.Popen(
                [python, "app.py", "--host", "0.0.0.0", "--port", str(port), "--data", str(data_dir)],
                cwd=ROOT,
                stdout=log_file,
                stderr=log_file,
                creationflags=0x00000010 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            )
    elif env == "plain":
        port = _port()
        python = _venv_python(ROOT)
        data_dir = ROOT / "data"
        data_dir.mkdir(exist_ok=True)
        log(f"Starting the server in the background (port {port}) …")
        log_file = open(data_dir / "server.log", "ab")
        proc = subprocess.Popen(
            [python, "app.py", "--host", "0.0.0.0", "--port", str(port), "--data", str(data_dir)],
            cwd=ROOT,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        (data_dir / "server.pid").write_text(str(proc.pid))
    else:
        log("Docker container: the update must be applied from the host machine")


def replace_files(src: Path, dst: Path) -> int:
    """Copy src → dst, preserving data/, .venv/ and logs."""
    copied = 0
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.name in SKIP_FILES or path.name.endswith((".log", ".pyc")):
            continue
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def sync_dependencies(dst: Path) -> None:
    req = dst / "requirements.txt"
    if not req.exists():
        return
    sha = hashlib.sha256(req.read_bytes()).hexdigest()
    marker = dst / "data" / ".requirements_sha"
    current = marker.read_text().strip() if marker.exists() else ""
    if current == sha:
        log("requirements.txt unchanged — skipping dependency install")
        return
    python = _venv_python(dst)
    log("Installing dependencies (pip install -r requirements.txt) …")
    proc = _run([python, "-m", "pip", "install", "-r", str(req)], cwd=dst, timeout=900)
    if proc.returncode != 0:
        log(f"pip failed:\n{proc.stderr[-2000:]}")
        raise SystemExit(1)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(sha)


def wait_health(port: int, timeout: int = HEALTH_TIMEOUT) -> dict | None:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            time.sleep(2)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bookmarks auto-updater (GitHub).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--check", action="store_true", help="only check for a new version")
    parser.add_argument("--yes", action="store_true", help="update without asking")
    parser.add_argument("--force", action="store_true", help="update even if already up to date")
    parser.add_argument("--source", help="install from a specific archive URL (zip)")
    args = parser.parse_args(argv)

    current = current_version()
    log(f"Current version: {current}")

    if args.source:
        latest = {"version": "?", "url": args.source, "source": "manual-url"}
    else:
        latest = fetch_latest()
        if latest is None:
            log("Could not reach GitHub — check the internet connection and try again")
            return 1
        log(f"Newest version on GitHub: {latest['version']} (source: {latest['source']})")

    if args.check:
        if args.source:
            print(json.dumps({"current": current, "latest": latest["version"], "source": latest["source"]}))
            return 0
        if (parse_version(latest["version"]) or (0,)) > (parse_version(current) or (0,)):
            print(json.dumps({"current": current, "latest": latest["version"], "available": True}))
            return 0
        print(json.dumps({"current": current, "latest": latest["version"], "available": False}))
        return 0

    if not args.force and (parse_version(latest["version"]) or (0,)) <= (parse_version(current) or (0,)):
        log("Already up to date.")
        return 0

    if not args.yes:
        answer = input(f"Update {current} -> {latest['version']}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            log("Cancelled.")
            return 0

    env = detect_env()
    log(f"Environment: {env}")
    if env == "docker-inside":
        log("The app runs inside a Docker container.")
        log("Run the update from the host machine (the installer does this via SSH),")
        log("or on the host: cd <project dir> && docker compose up -d --build")
        return 1

    work = Path(tempfile.mkdtemp(prefix="bms-upd-"))
    try:
        if latest.get("zip_path"):
            zip_path = Path(latest["zip_path"])
        else:
            log("Downloading the archive …")
            zip_path = http_download(latest["url"], work / "update.zip")
        log("Extracting …")
        src = extract_zip(zip_path)
        stop_server(env)
        log("Replacing the program files (data/ and .venv/ are preserved) …")
        copied = replace_files(src, ROOT)
        log(f"{copied} files copied")
        sync_dependencies(ROOT)
        start_server(env)
        health = wait_health(_port())
        if health and health.get("ok"):
            log(f"Done! Version {health.get('version')} is running: http://127.0.0.1:{_port()}/health OK")
            return 0
        log(f"Health check failed after {HEALTH_TIMEOUT}s — check the server logs")
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
