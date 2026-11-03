#!/usr/bin/env python3
"""Bookmarks auto-updater (GitHub).

Usage:
  python update.py --check            only check for a new version
  python update.py --yes              update if a new version is available
  python update.py --force --yes      update unconditionally (reinstall files)
  python update.py --source <url> --yes
                                      install from a specific archive URL
                                      (a zip or tar with the project files)

How it works:
  1. detects the environment: Windows / systemd / Docker / plain;
  2. finds the newest version (the highest one wins):
     - the update/ folder in the install dir or on GitHub
       (archives named update_vX_X_X.tar — the primary source);
     - otherwise a release with a .zip asset, or a release tag archive;
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
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = "evgeniy7f2/Bookmarks"
GITHUB_API = f"https://api.github.com/repos/{REPO}"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"
BRANCH_ZIP = f"https://github.com/{REPO}/archive/refs/heads/main.zip"
HEALTH_TIMEOUT = 90
# The update/ folder holds archives named update_vX_X_X.tar (the primary
# update source: the user uploads a new tar there on GitHub, or drops it
# into the local update/ folder for an offline update).
UPDATE_FOLDER = "update"
UPDATE_TAR_RE = re.compile(r"^update_v(\d+)_(\d+)_(\d+)\.tar$")
# How long the GitHub update/ listing and the full fetch_latest() result
# stay cached (seconds) — the ticker polls /api/update/check periodically
# and the unauthenticated GitHub API is limited to 60 req/h.
UPDATE_CACHE_TTL = 300
FETCH_CACHE_TTL = 120
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


def update_folder_versions(folder: Path) -> dict | None:
    """The newest update_vX_X_X.tar in a local update/ folder (offline update).

    Returns a candidate dict (with local_path) or None if no versioned tar.
    """
    try:
        paths = list(folder.glob("update_v*.tar"))
    except OSError:
        return None
    best: tuple[tuple[int, ...], Path] | None = None
    for path in paths:
        m = UPDATE_TAR_RE.match(path.name)
        if not m:
            continue
        ver = tuple(int(x) for x in m.groups())
        if best is None or ver > best[0]:
            best = (ver, path)
    if best is None:
        return None
    ver, path = best
    return {
        "version": ".".join(str(x) for x in ver),
        "url": path.as_uri(),
        "source": "update-folder",
        "kind": "tar",
        "local_path": str(path),
    }


_update_dir_cache: dict = {"ts": 0.0, "checked": False, "candidate": None}


def fetch_update_folder_github() -> dict | None:
    """The newest update_vX_X_X.tar in the repo's update/ folder on GitHub.

    The folder is looked up at the repo root first (update/); if it is not
    there, the ubuntu_sp/update/ folder is checked (the repo may keep the
    whole ubuntu_sp/ distribution tree as a subfolder).

    The folder listing is cached for UPDATE_CACHE_TTL seconds: the ticker
    polls /api/update/check while the app is open and the unauthenticated
    GitHub API allows only 60 requests/hour.
    """
    now = time.time()
    if _update_dir_cache["checked"] and now - _update_dir_cache["ts"] < UPDATE_CACHE_TTL:
        return _update_dir_cache["candidate"]
    best: tuple[tuple[int, ...], str, str] | None = None  # (version, name, folder)
    for folder in (UPDATE_FOLDER, f"ubuntu_sp/{UPDATE_FOLDER}"):
        try:
            items = http_json(f"{GITHUB_API}/contents/{folder}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue  # no folder at this location — try the next one
            log(f"update/ check ({folder}): {exc.__class__.__name__}")
            break
        except Exception as exc:  # no network
            log(f"update/ check ({folder}): {exc.__class__.__name__}")
            break
        if not isinstance(items, list):
            break
        for item in items:
            if item.get("type") != "file":
                continue
            m = UPDATE_TAR_RE.match(item.get("name") or "")
            if not m:
                continue
            ver = tuple(int(x) for x in m.groups())
            if best is None or ver > best[0]:
                best = (ver, item["name"], folder)
        if best is not None:
            break  # the folder exists and holds versioned tars
    candidate = None
    if best is not None:
        ver, name, folder = best
        candidate = {
            "version": ".".join(str(x) for x in ver),
            "url": f"{RAW_BASE}/{folder}/{urllib.request.quote(name)}",
            "source": "update-folder",
            "kind": "tar",
        }
    _update_dir_cache.update({"ts": now, "checked": True, "candidate": candidate})
    return candidate


_fetch_cache: dict = {"ts": 0.0, "result": None}


def fetch_latest(force: bool = False) -> dict | None:
    """Find the newest version for the updater.

    Sources (the highest version wins):
      1) the local update/ folder — update_vX_X_X.tar (offline update);
      2) the update/ folder on GitHub — update_vX_X_X.tar;
      3) the latest release (.zip asset or the tag archive);
      4) the main branch archive (version read from bookmarks/util.py).

    The result is cached for FETCH_CACHE_TTL seconds unless force=True.
    Returns {"version", "url", "source", "kind", "zip_path"?, "local_path"?} or None.
    """
    now = time.time()
    if not force and now - _fetch_cache["ts"] < FETCH_CACHE_TTL:
        return _fetch_cache["result"]
    result = _fetch_latest_uncached()
    _fetch_cache.update({"ts": now, "result": result})
    return result


def _fetch_latest_uncached() -> dict | None:
    candidates: list[dict] = []

    # 1) local update/ folder (no network needed)
    local = update_folder_versions(ROOT / UPDATE_FOLDER)
    if local:
        candidates.append(local)

    # 2) the update/ folder on GitHub (update_vX_X_X.tar)
    gh = fetch_update_folder_github()
    if gh:
        candidates.append(gh)

    # 3) latest release (asset zip, or the tag archive as fallback)
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
                {
                    "version": ".".join(map(str, ver)),
                    "url": url,
                    "source": "release",
                    "kind": "zip",
                    "tag": tag,
                }
            )
    except Exception as exc:
        log(f"release check: {exc.__class__.__name__} (fallback to the main branch)")

    # 4) main branch archive (version read from bookmarks/util.py)
    tmp = _mkdtemp()
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
                            "kind": "zip",
                            "zip_path": str(zip_path),
                            "zip_dir": str(tmp),
                        }
                    )
    except Exception as exc:
        log(f"branch check: {exc.__class__.__name__}")
    finally:
        if not candidates or candidates[-1].get("zip_path") != str(tmp / "main.zip"):
            shutil.rmtree(tmp, ignore_errors=True)

    if not candidates:
        return None
    best = _pick_best(candidates)
    for cand in candidates:
        if cand is not best and cand.get("zip_dir"):
            shutil.rmtree(cand["zip_dir"], ignore_errors=True)
    return best


def _pick_best(candidates: list[dict], keep_zip: str | None = None) -> dict:
    # highest version wins; the branch candidate already carries its
    # downloaded zip (zip_path), the release candidate downloads it later.
    return max(candidates, key=lambda c: parse_version(c["version"]) or (0,))


def _mkdtemp() -> Path:
    """Temp dir under ROOT/data (not /tmp).

    Under systemd with PrivateTmp=true the service runs in a private /tmp
    mount namespace that is torn down on `systemctl stop`. The updater stops
    the service mid-run, so an extraction dir in that private /tmp is deleted
    before the files are copied (silently 0 files, update no-ops). ROOT/data
    is on the real filesystem and survives the stop.
    """
    base = ROOT / "data"
    try:
        base.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="bms-upd-", dir=str(base)))
    except OSError:
        return Path(tempfile.mkdtemp(prefix="bms-upd-"))


def extract_zip(zip_path: Path) -> Path:
    """Extract the project archive; returns the directory containing app.py."""
    tmp = _mkdtemp()
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp)
    candidates = [p for p in tmp.rglob("app.py")]
    if not candidates:
        raise SystemExit("[update] app.py not found inside the archive")
    return candidates[0].parent


def extract_tar(tar_path: Path) -> Path:
    """Extract the project tar archive; returns the directory containing app.py."""
    tmp = _mkdtemp()
    with tarfile.open(tar_path) as tf:
        tf.extractall(tmp)
    candidates = [p for p in tmp.rglob("app.py")]
    if not candidates:
        raise SystemExit("[update] app.py not found inside the archive")
    return candidates[0].parent


def _archive_kind(latest: dict) -> str:
    kind = latest.get("kind")
    if kind in ("tar", "zip"):
        return kind
    return "tar" if str(latest.get("url", "")).lower().endswith(".tar") else "zip"


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
        proc = _run(["systemctl", "stop", "bookmarks"])
        if proc.returncode != 0:
            raise SystemExit(f"[update] systemctl stop failed: {proc.stderr.strip()}")
        # Fail fast if the unit is somehow still up: overwriting the files of
        # a live server leaves a broken install. (With the default
        # KillMode=control-group the stop used to kill this process along
        # with the service cgroup, so the update died right here.)
        state = _run(["systemctl", "show", "-p", "ActiveState", "--value", "bookmarks"])
        active = (state.stdout or "").strip()
        if state.returncode == 0 and active not in ("inactive", "failed"):
            raise SystemExit(f"[update] service still {active} after stop — aborting")
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
        proc = _run(["systemctl", "start", "bookmarks"])
        if proc.returncode != 0:
            raise SystemExit(f"[update] systemctl start failed: {proc.stderr.strip()}")
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

    work: Path | None = None
    src: Path | None = None
    try:
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

        work = _mkdtemp()
        kind = _archive_kind(latest)
        if latest.get("local_path"):
            archive_path = Path(latest["local_path"])  # local update/ tar: no download
        elif latest.get("zip_path"):
            archive_path = Path(latest["zip_path"])
        else:
            log("Downloading the archive …")
            archive_path = http_download(latest["url"], work / ("update.tar" if kind == "tar" else "update.zip"))
        log("Extracting …")
        src = extract_tar(archive_path) if kind == "tar" else extract_zip(archive_path)
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
        if src is not None:
            shutil.rmtree(src, ignore_errors=True)
        if latest.get("zip_dir"):
            shutil.rmtree(latest["zip_dir"], ignore_errors=True)
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
